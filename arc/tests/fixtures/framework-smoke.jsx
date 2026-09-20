// Integration fixture only. Not shipped as a generated application's template.
import {useState} from 'react';
import {Routes, Route, Link} from 'react-router';
import {Dialog, DropdownMenu, Checkbox} from 'radix-ui';
import {useForm} from 'react-hook-form';
import {zodResolver} from '@hookform/resolvers/zod';
import {z} from 'zod';
import {DayPicker} from 'react-day-picker';
import 'react-day-picker/style.css';
import {format} from 'date-fns';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {useEditor, EditorContent} from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Decimal from 'decimal.js';
import useEmblaCarousel from 'embla-carousel-react';
import {Check} from 'lucide-react';

function Fixture() {
  const [checked, setChecked] = useState(false);
  const [open, setOpen] = useState(false);
  const [count, setCount] = useState(0);
  const [submitted, setSubmitted] = useState('');
  const [day, setDay] = useState(new Date(2026, 0, 10));
  const {register, handleSubmit, formState: {errors}} = useForm({resolver: zodResolver(z.object({name: z.string().min(1, 'Required')}))});
  const editor = useEditor({extensions: [StarterKit], content: '<p>Editable text</p>', immediatelyRender: false,
    editorProps: {attributes: {role: 'textbox', 'aria-label': 'Document body', 'aria-multiline': 'true'}}});
  const [carouselRef] = useEmblaCarousel();
  return <main>
    <h1 className="text-3xl">Framework smoke</h1>
    <Link to="/details">Details</Link>
    <label>Display mode<select defaultValue="compact"><option value="compact">Compact</option><option value="expanded">Expanded</option></select></label>
    <label><input type="checkbox" checked={checked} onChange={event => setChecked(event.target.checked)} />Native flag</label>
    <Checkbox.Root aria-label="Radix flag" checked={checked} onCheckedChange={value => setChecked(value === true)}><Checkbox.Indicator><Check aria-hidden="true" /></Checkbox.Indicator></Checkbox.Root>
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild><button>Open editor</button></Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay style={{position: 'fixed', inset: 0, background: '#0008', zIndex: 10}} />
        <Dialog.Content style={{position: 'fixed', top: 30, left: 30, padding: 20, background: 'white', zIndex: 11}}>
          <Dialog.Title>Editor</Dialog.Title><Dialog.Description>Edit a draft.</Dialog.Description>
          <label>Draft<input defaultValue="draft" /></label>
          <Dialog.Close asChild><button>Close editor</button></Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild><button>Actions</button></DropdownMenu.Trigger>
      <DropdownMenu.Portal><DropdownMenu.Content style={{background: 'white'}}>
        <DropdownMenu.Item onSelect={() => setCount(n => n + 1)}>Increment once</DropdownMenu.Item>
      </DropdownMenu.Content></DropdownMenu.Portal>
    </DropdownMenu.Root>
    <output aria-label="Selections">{count}</output>
    <form onSubmit={handleSubmit(data => setSubmitted(data.name))}>
      <label>Name<input {...register('name')} /></label><button>Submit form</button>
      {errors.name && <p role="alert">{errors.name.message}</p>}
    </form><output aria-label="Submitted">{submitted}</output>
    <DayPicker mode="single" selected={day} onSelect={setDay} defaultMonth={day} />
    <output aria-label="Date">{day ? format(day, 'yyyy-MM-dd') : ''}</output>
    <Markdown remarkPlugins={[remarkGfm]}>{'**Markdown works**'}</Markdown>
    <EditorContent editor={editor} />
    <output aria-label="Decimal">{new Decimal('0.1').plus('0.2').toString()}</output>
    <div ref={carouselRef} style={{overflow: 'hidden'}}><div style={{display: 'flex'}}><div style={{flex: '0 0 100%'}}>Slide one</div><div style={{flex: '0 0 100%'}}>Slide two</div></div></div>
  </main>;
}

export default function App() {
  return <Routes><Route path="/" element={<Fixture />} /><Route path="/details" element={<h1>Local deep route</h1>} /></Routes>;
}
