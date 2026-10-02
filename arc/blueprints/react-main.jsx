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
  // Fresh apps use ordinary route updates so entry controls do not wait on a
  // deferred transition. This is a default, not a ban on Suspense/transitions:
  // if enabled later, verify pending UI and the destination's usable controls.
  <RuntimeErrorBoundary><BrowserRouter useTransitions={false}><App /></BrowserRouter></RuntimeErrorBoundary>
);
