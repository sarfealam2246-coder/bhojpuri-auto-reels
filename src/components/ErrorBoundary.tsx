import React from 'react';

interface State {
  hasError: boolean;
  message: string;
}

export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, message: '' };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message || 'Unknown error' };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#F0F2F5] flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-white border border-[#CED0D4] rounded-xl p-5 text-center">
            <h2 className="text-lg font-bold text-[#1877F2] mb-2">Bhojpuri ReelStudio</h2>
            <p className="text-sm text-[#65676B] mb-4">{this.state.message}</p>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 rounded-lg bg-[#1877F2] text-white text-sm font-semibold"
            >
              App Dobara Chalayein
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
