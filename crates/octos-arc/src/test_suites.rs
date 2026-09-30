//! Source-reviewed, frozen internal suites, embedded even in debug builds.
//! Extraction never upgrades source review into a measured product pass.
use clap::Args;
use eyre::{Context, Result, ensure};
use rust_embed::Embed;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs,
    path::{Component, Path, PathBuf},
};

#[derive(Embed)]
#[folder = "../../arc/frozen-tests/"]
struct Suites;

#[derive(Debug, Args)]
pub struct TestsCommand {
    /// Print the embedded suite catalogue as JSON.
    #[arg(long, conflicts_with_all = ["name", "output_dir", "requirements_sha256"])]
    pub list: bool,
    /// Canonical ARC task ID, e.g. hackathon--github.
    #[arg(long, required_unless_present = "list")]
    pub name: Option<String>,
    /// New suite directory (an identical existing extraction is reusable).
    #[arg(long, required_unless_present = "list")]
    pub output_dir: Option<PathBuf>,
    /// SHA256 of the original requirement tree's sorted compact UTF-8 JSON.
    #[arg(long, required_unless_present = "list")]
    pub requirements_sha256: Option<String>,
}

fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn safe_path(path: &str) -> bool {
    !path.is_empty()
        && !path.contains('\\')
        && Path::new(path)
            .components()
            .all(|c| matches!(c, Component::Normal(_)))
}
fn read_json(path: &str) -> Result<Value> {
    let file = Suites::get(path).ok_or_else(|| eyre::eyre!("Missing embedded {path}"))?;
    Ok(serde_json::from_slice(&file.data)?)
}
pub fn catalogue() -> Result<Value> {
    read_json("manifest.json")
}

fn content(name: &str, fingerprint: &str) -> Result<(Value, BTreeMap<String, Vec<u8>>)> {
    let catalogue = catalogue()?;
    let entry = catalogue["suites"]
        .get(name)
        .ok_or_else(|| eyre::eyre!("Unknown embedded test suite: {name}"))?;
    ensure!(
        entry["requirements_sha256"].as_str() == Some(fingerprint),
        "Requirements do not match frozen suite {name}"
    );
    ensure!(safe_path(name) && !name.contains('/'), "Invalid suite name");
    let manifest = read_json(&format!("{name}/suite-origin.json"))?;
    ensure!(
        manifest["official"] == false
            && manifest["review_status"] == "reviewed"
            && manifest["frozen"] == true,
        "Suite is not reviewed and frozen"
    );
    ensure!(
        manifest["requirements_sha256"] == entry["requirements_sha256"],
        "Suite identity mismatch"
    );
    let files = manifest["files"]
        .as_object()
        .ok_or_else(|| eyre::eyre!("Missing file hashes"))?;
    let mut output = BTreeMap::new();
    for (rel, expected) in files {
        ensure!(safe_path(rel), "Unsafe embedded path: {rel}");
        let file = Suites::get(&format!("{name}/{rel}"))
            .ok_or_else(|| eyre::eyre!("Missing suite file: {rel}"))?;
        ensure!(
            expected.as_str() == Some(hash(&file.data).as_str()),
            "Frozen file hash mismatch: {rel}"
        );
        output.insert(rel.clone(), file.data.into_owned());
    }
    let review: Value = serde_json::from_slice(
        output
            .get("review.json")
            .ok_or_else(|| eyre::eyre!("Missing review record"))?,
    )?;
    let cases = review["cases"]
        .as_array()
        .ok_or_else(|| eyre::eyre!("Missing case reviews"))?;
    ensure!(
        !cases.is_empty()
            && cases
                .iter()
                .all(|row| row["status"] == "reviewed" && row["frozen"] == true),
        "Unreviewed case in frozen suite"
    );
    for row in cases {
        let rel = row["file"]
            .as_str()
            .ok_or_else(|| eyre::eyre!("Missing reviewed spec path"))?;
        let bytes = output
            .get(rel)
            .ok_or_else(|| eyre::eyre!("Reviewed spec missing: {rel}"))?;
        ensure!(
            row["file_sha256"].as_str() == Some(hash(bytes).as_str()),
            "Reviewed spec changed: {rel}"
        );
    }
    ensure!(
        cases.len() as u64 == manifest["case_count"].as_u64().unwrap_or(0),
        "Case count mismatch"
    );
    let business: Value = serde_json::from_slice(
        output
            .get("business-review.json")
            .ok_or_else(|| eyre::eyre!("Missing frozen business review"))?,
    )?;
    ensure!(
        business["review_status"] == "reviewed"
            && business["frozen"] == true
            && business["official"] == false
            && business["requirements_sha256"] == manifest["requirements_sha256"],
        "Business model is not source-reviewed for this requirement tree"
    );
    for rel in [
        "app-design.json",
        "domain-contracts.json",
        "requirement-contracts.json",
        "test-obligations.json",
    ] {
        let bytes = output
            .get(rel)
            .ok_or_else(|| eyre::eyre!("Missing frozen business file: {rel}"))?;
        ensure!(
            business["files"][rel].as_str() == Some(hash(bytes).as_str()),
            "Reviewed business model changed: {rel}"
        );
    }
    output.insert(
        "suite-origin.json".into(),
        serde_json::to_vec_pretty(&manifest)?,
    );
    Ok((manifest, output))
}

fn check_existing(directory: &Path, files: &BTreeMap<String, Vec<u8>>) -> Result<()> {
    ensure!(
        fs::symlink_metadata(directory)?.is_dir(),
        "Suite destination must be a regular directory"
    );
    fn walk(directory: &Path, prefix: &Path, output: &mut BTreeMap<String, Vec<u8>>) -> Result<()> {
        for entry in fs::read_dir(directory)? {
            let entry = entry?;
            let rel = prefix.join(entry.file_name());
            let kind = entry.file_type()?;
            ensure!(!kind.is_symlink(), "Symlink in frozen suite destination");
            if kind.is_dir() {
                walk(&entry.path(), &rel, output)?;
            } else {
                ensure!(kind.is_file(), "Unexpected suite destination file type");
                output.insert(
                    rel.to_string_lossy().replace('\\', "/"),
                    fs::read(entry.path())?,
                );
            }
        }
        Ok(())
    }
    let mut existing = BTreeMap::new();
    walk(directory, Path::new(""), &mut existing)?;
    ensure!(
        &existing == files,
        "Existing suite differs from frozen content; choose a new destination"
    );
    Ok(())
}

pub fn extract(name: &str, fingerprint: &str, directory: &Path) -> Result<Value> {
    // Validate every embedded byte before creating or changing the destination.
    let (manifest, files) = content(name, fingerprint)?;
    let parent = directory
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    // Refuse existing symlink ancestors before any filesystem mutation.
    for ancestor in parent.ancestors() {
        if let Ok(meta) = fs::symlink_metadata(ancestor) {
            ensure!(
                !meta.file_type().is_symlink(),
                "Symlink parent of suite destination"
            );
        }
    }
    fs::create_dir_all(parent)?;
    // Recheck the newly created parent chain.
    for ancestor in parent.ancestors() {
        if !ancestor.as_os_str().is_empty() {
            ensure!(
                !fs::symlink_metadata(ancestor)?.file_type().is_symlink(),
                "Symlink parent of suite destination"
            );
        }
    }
    if fs::symlink_metadata(directory).is_ok() {
        check_existing(directory, &files)?;
    } else {
        let stage = tempfile::tempdir_in(parent)?;
        for (rel, bytes) in &files {
            let target = stage.path().join(rel);
            fs::create_dir_all(target.parent().expect("file parent"))?;
            fs::write(target, bytes)?;
        }
        // Same-filesystem rename exposes the complete directory together. A
        // non-empty concurrent destination causes an error rather than a merge.
        fs::rename(stage.path(), directory).wrap_err("Cannot publish frozen suite directory")?;
    }
    Ok(
        json!({"name":name,"directory":fs::canonicalize(directory)?,"official":false,"review_status":"reviewed","frozen":true,"case_count":manifest["case_count"],"spec_count":manifest["spec_count"],"requirements_sha256":fingerprint,"manifest_sha256":hash(&files["suite-origin.json"])}),
    )
}

/// Match Python's sorted compact UTF-8 JSON independently of serde feature flags.
pub fn requirements_fingerprint(value: &Value) -> String {
    fn compact(value: &Value) -> String {
        match value {
            Value::Object(map) => {
                let sorted: BTreeMap<_, _> = map.iter().collect();
                format!(
                    "{{{}}}",
                    sorted
                        .into_iter()
                        .map(|(key, val)| format!(
                            "{}:{}",
                            serde_json::to_string(key).expect("JSON key"),
                            compact(val)
                        ))
                        .collect::<Vec<_>>()
                        .join(",")
                )
            }
            Value::Array(array) => format!(
                "[{}]",
                array.iter().map(compact).collect::<Vec<_>>().join(",")
            ),
            _ => serde_json::to_string(value).expect("JSON value"),
        }
    }
    hash(compact(value).as_bytes())
}

pub fn note_for_extracted(directory: &Path, tree: &Value) -> Result<Option<String>> {
    let marker = directory.join("suite-origin.json");
    if !marker.is_file() {
        return Ok(None);
    }
    let origin: Value = serde_json::from_slice(&fs::read(marker)?)?;
    let Some(name) = origin["name"].as_str() else {
        return Ok(None);
    };
    if catalogue()?["suites"].get(name).is_none() {
        return Ok(None);
    }
    let (_, files) = content(name, &requirements_fingerprint(tree))?;
    check_existing(directory, &files)?;
    Ok(Some(format!(
        "SOURCE-REVIEWED FROZEN INTERNAL TEST SUITE at {}. All cases were source-reviewed before this run; do not regenerate or modify them. This is not an official benchmark suite or a measured pass. Requirements remain authoritative. Read {}/fixtures.json and {}/README.md before generation to provision independent public seeds and role accounts; no private/reset API is required. Use the frozen source-reviewed app-design.json, domain-contracts.json, requirement-contracts.json and test-obligations.json in that directory directly; do not regenerate or edit those business models. Their shared schemas are design proposals; implementation paths remain choices.\n",
        directory.display(),
        directory.display(),
        directory.display()
    )))
}

/// Include the relevant shared model in codegen/tool turns; full files remain
/// available when a source block is too large for a compact turn.
pub fn business_context(directory: &Path, node_id: Option<&str>) -> Result<String> {
    let Some(node) = node_id else {
        return Ok(String::new());
    };
    let model: Value = serde_json::from_slice(&fs::read(directory.join("app-design.json"))?)?;
    let relevant = |value: &&Value| {
        value["requirements"].as_array().is_some_and(|ids| {
            ids.iter()
                .any(|id| id.as_str() == Some(node) || id.as_str() == Some("ROOT"))
        })
    };
    let selected = |key: &str| {
        model[key]
            .as_array()
            .map(|rows| rows.iter().filter(relevant).cloned().collect::<Vec<_>>())
            .unwrap_or_default()
    };
    let domains = selected("domain_contracts");
    let data: BTreeMap<_, _> = domains
        .iter()
        .filter_map(|row| row["entity"].as_str())
        .map(|name| (name, model["data_model"][name].clone()))
        .collect();
    let context = json!({"data_model":data,"domain_contracts":domains,"contracts":selected("contracts"),"commands":selected("commands"),"notes":model["notes"]}).to_string();
    if context.chars().count() > 60_000 {
        return Ok(format!(
            "Read the complete frozen shared business model for {node} in {}/app-design.json before implementation; the full source clauses are intentionally retained there.\n",
            directory.display()
        ));
    }
    Ok(format!(
        "FROZEN SHARED BUSINESS MODEL (source-reviewed proposal, original requirements authoritative): {context}\n"
    ))
}

pub fn execute(command: TestsCommand) -> Result<()> {
    if command.list {
        println!("{}", catalogue()?);
        return Ok(());
    }
    let result = extract(
        command.name.as_deref().expect("clap name"),
        command
            .requirements_sha256
            .as_deref()
            .expect("clap fingerprint"),
        command.output_dir.as_deref().expect("clap output"),
    )
    .wrap_err("Cannot materialize reviewed embedded suite")?;
    println!("{result}");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fingerprint(name: &str) -> String {
        catalogue().unwrap()["suites"][name]["requirements_sha256"]
            .as_str()
            .unwrap()
            .into()
    }
    #[test]
    fn every_catalogued_suite_extracts_reviewed_complete_content_and_is_reusable() {
        let root = tempfile::tempdir().unwrap();
        for name in ["hackathon--github", "hackathon--sheet"] {
            let directory = root.path().join(name);
            let receipt = extract(name, &fingerprint(name), &directory).unwrap();
            assert_eq!(receipt["review_status"], "reviewed");
            assert_eq!(receipt["frozen"], true);
            assert_eq!(receipt["official"], false);
            let specs = fs::read_dir(&directory)
                .unwrap()
                .filter_map(|p| p.ok())
                .filter(|p| p.file_name().to_string_lossy().ends_with(".spec.ts"))
                .count();
            assert_eq!(specs as u64, receipt["spec_count"].as_u64().unwrap());
            assert!(directory.join("helpers.ts").is_file());
            assert!(directory.join("fixtures.json").is_file());
            extract(name, &fingerprint(name), &directory).unwrap();
        }
    }
    #[test]
    fn unknown_name_and_requirement_mismatch_create_no_destination() {
        let root = tempfile::tempdir().unwrap();
        let directory = root.path().join("absent");
        assert!(extract("unknown", "", &directory).is_err());
        assert!(!directory.exists());
        assert!(extract("hackathon--github", "wrong", &directory).is_err());
        assert!(!directory.exists());
        assert!(extract("../hackathon--github", "wrong", &directory).is_err());
    }
    #[test]
    fn extracted_provenance_binds_the_original_tree_and_rejects_modified_files() {
        let root = tempfile::tempdir().unwrap();
        for name in ["hackathon--github", "hackathon--sheet"] {
            let directory = root.path().join(name);
            extract(name, &fingerprint(name), &directory).unwrap();
            let tree: Value =
                serde_yml::from_slice(&fs::read(directory.join("requirements.yaml")).unwrap())
                    .unwrap();
            assert_eq!(requirements_fingerprint(&tree), fingerprint(name));
            let note = note_for_extracted(&directory, &tree).unwrap().unwrap();
            assert!(note.contains("not an official benchmark suite or a measured pass"));
            assert!(note.contains("fixtures.json"));
            assert!(note.contains("app-design.json"));
            let context = business_context(&directory, Some("REQ-1-1-1")).unwrap();
            assert!(context.contains("FROZEN SHARED BUSINESS MODEL"));
            assert!(context.contains("data_model"));
            let mut changed = tree.clone();
            changed["description"] = json!("Changed requirement");
            assert!(note_for_extracted(&directory, &changed).is_err());
            fs::write(directory.join("helpers.ts"), "attempted rewrite").unwrap();
            assert!(note_for_extracted(&directory, &tree).is_err());
        }
        assert!(
            note_for_extracted(root.path(), &json!({}))
                .unwrap()
                .is_none()
        );
    }
    #[test]
    fn changed_destination_is_never_overwritten_or_mixed_with_the_suite() {
        let root = tempfile::tempdir().unwrap();
        let directory = root.path().join("suite");
        let fp = fingerprint("hackathon--sheet");
        extract("hackathon--sheet", &fp, &directory).unwrap();
        fs::write(directory.join("helpers.ts"), "user data").unwrap();
        assert!(extract("hackathon--sheet", &fp, &directory).is_err());
        assert_eq!(
            fs::read_to_string(directory.join("helpers.ts")).unwrap(),
            "user data"
        );
    }
    #[cfg(unix)]
    #[test]
    fn symlink_destinations_and_parents_are_refused() {
        let root = tempfile::tempdir().unwrap();
        let target = root.path().join("real");
        fs::create_dir(&target).unwrap();
        let link = root.path().join("link");
        std::os::unix::fs::symlink(&target, &link).unwrap();
        assert!(extract("hackathon--sheet", &fingerprint("hackathon--sheet"), &link).is_err());
        assert!(
            extract(
                "hackathon--sheet",
                &fingerprint("hackathon--sheet"),
                &link.join("suite")
            )
            .is_err()
        );
        assert!(!target.join("suite").exists());
    }
}
