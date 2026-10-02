// Optional strict query parsing. No domain fields, visibility or ownership defaults.
function optionalBoolean(value) {
  if (value === undefined) return undefined;
  if (value === true || value === 'true') return true;
  if (value === false || value === 'false') return false;
  const error = new Error('Expected true or false');
  error.status = 400;
  throw error;
}

// Caller resolves view defaults ONCE, then passes only supported boolean fields.
// Undefined is not a constraint; false is an explicit constraint. Never coerce
// missing record fields to false: establish record defaults in the data model.
function matchesFlags(record, flags) {
  return Object.entries(flags).every(([field, value]) => {
    if (value === undefined) return true;
    if (typeof value !== 'boolean') throw new TypeError('Flags must be booleans');
    return record[field] === value;
  });
}

module.exports = {optionalBoolean, matchesFlags};
