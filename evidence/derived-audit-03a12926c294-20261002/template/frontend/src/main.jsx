import React from 'react';
import {createRoot} from 'react-dom/client';
import {BrowserRouter} from 'react-router';
import App from './App.jsx';
import './style.css';

class RuntimeErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {failed: false};
  }

  static getDerivedStateFromError() {
    return {failed: true};
  }

  render() {
    if (this.state.failed) {
      return <main data-arc-runtime-error="true" role="alert">
        <h1>This page could not be displayed</h1>
        <p>Reload the page to try again.</p>
        <button type="button" onClick={() => window.location.reload()}>Reload</button>
      </main>;
    }
    return this.props.children;
  }
}

createRoot(document.getElementById('app')).render(
  <RuntimeErrorBoundary><BrowserRouter><App /></BrowserRouter></RuntimeErrorBoundary>
);
