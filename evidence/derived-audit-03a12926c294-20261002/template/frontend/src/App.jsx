import {Routes, Route} from 'react-router';
import Home from './pages/Home.jsx';
import Editor from './pages/Editor.jsx';
import CreateWorkbook from './pages/CreateWorkbook.jsx';

// Domain pages and behavior are implemented from the requirement tree.
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/workbooks/new" element={<CreateWorkbook />} />
      <Route path="/workbooks/:workbookId" element={<Editor />} />
    </Routes>
  );
}
