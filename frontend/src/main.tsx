import React, { Component, ReactNode } from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    const { error } = this.state;
    if (error) {
      const isChunkError = (error as any).message?.includes("Failed to fetch dynamically imported module")
        || (error as any).message?.includes("Loading chunk");
      return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50">
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-8 max-w-md text-center space-y-4">
            <div className="text-2xl font-bold text-slate-800">Something went wrong</div>
            {isChunkError ? (
              <>
                <p className="text-slate-500 text-sm">
                  The app was updated. Please refresh to load the latest version.
                </p>
                <button
                  onClick={() => window.location.reload()}
                  className="px-5 py-2 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700 transition-colors"
                >
                  Refresh now
                </button>
              </>
            ) : (
              <>
                <p className="text-slate-500 text-sm font-mono text-left bg-slate-50 rounded-lg p-3">
                  {(error as any).message}
                </p>
                <button
                  onClick={() => window.location.reload()}
                  className="px-5 py-2 bg-slate-700 text-white rounded-lg text-sm font-semibold hover:bg-slate-800 transition-colors"
                >
                  Reload page
                </button>
              </>
            )}
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
