import { useState, useRef } from 'react';

type UploadMode = 'url' | 'file';

interface UploadResult {
  success: boolean;
  path?: string;
  type?: string;
  size?: string;
  error?: string;
}

interface Props {
  onUploadComplete?: (result: UploadResult) => void;
}

export function UploadPanel({ onUploadComplete }: Props) {
  const [mode, setMode] = useState<UploadMode>('url');
  const [url, setUrl] = useState('');
  const [filename, setFilename] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleUpload = async () => {
    if (mode === 'url' && !url.trim()) return;
    if (mode === 'file' && !selectedFile) return;

    setIsUploading(true);
    setResult(null);

    try {
      let response: Response;

      if (mode === 'url') {
        response = await fetch('/api/upload', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            url: url.trim(),
            filename: filename.trim() || undefined,
          }),
        });
      } else {
        const formData = new FormData();
        formData.append('file', selectedFile!);
        if (filename.trim()) {
          formData.append('filename', filename.trim());
        }
        response = await fetch('/api/upload/file', {
          method: 'POST',
          body: formData,
        });
      }

      const data = await response.json();
      setResult(data);
      onUploadComplete?.(data);

      if (data.success) {
        setUrl('');
        setFilename('');
        setSelectedFile(null);
        if (fileInputRef.current) {
          fileInputRef.current.value = '';
        }
      }
    } catch (err) {
      const errorResult = {
        success: false,
        error: err instanceof Error ? err.message : 'Upload failed',
      };
      setResult(errorResult);
      onUploadComplete?.(errorResult);
    } finally {
      setIsUploading(false);
    }
  };

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text.startsWith('http://') || text.startsWith('https://')) {
        setUrl(text);
      }
    } catch {
      // Clipboard access denied
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      if (!filename) {
        setFilename(file.name);
      }
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 mb-2">
        <div className="w-1.5 h-1.5 rounded-full bg-blue-400" />
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          Upload File
        </h3>
      </div>

      {/* Mode Select */}
      <div className="flex gap-1 p-1 bg-surface-overlay rounded border border-border-subtle">
        <button
          onClick={() => setMode('url')}
          disabled={isUploading}
          className={`flex-1 px-3 py-1.5 text-xs font-medium rounded transition-colors ${
            mode === 'url'
              ? 'bg-accent/20 text-accent border border-accent/30'
              : 'text-text-muted hover:text-text-secondary'
          }`}
        >
          🔗 From URL
        </button>
        <button
          onClick={() => setMode('file')}
          disabled={isUploading}
          className={`flex-1 px-3 py-1.5 text-xs font-medium rounded transition-colors ${
            mode === 'file'
              ? 'bg-accent/20 text-accent border border-accent/30'
              : 'text-text-muted hover:text-text-secondary'
          }`}
        >
          📁 From Device
        </button>
      </div>

      {/* URL Mode */}
      {mode === 'url' && (
        <div className="space-y-2">
          <div className="flex gap-2">
            <input
              ref={inputRef}
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleUpload()}
              placeholder="Paste file URL..."
              disabled={isUploading}
              className="flex-1 bg-surface-overlay border border-border-subtle rounded px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors disabled:opacity-50"
            />
            <button
              onClick={handlePaste}
              disabled={isUploading}
              className="px-3 py-2 bg-surface-overlay border border-border-subtle rounded text-xs text-text-muted hover:text-text-secondary hover:border-accent/30 transition-colors disabled:opacity-50"
              title="Paste from clipboard"
            >
              📋
            </button>
          </div>
        </div>
      )}

      {/* File Mode */}
      {mode === 'file' && (
        <div className="space-y-2">
          <input
            ref={fileInputRef}
            type="file"
            onChange={handleFileSelect}
            disabled={isUploading}
            className="w-full bg-surface-overlay border border-border-subtle rounded px-3 py-2 text-sm text-text-primary file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-accent/20 file:text-accent file:text-xs file:font-medium file:cursor-pointer disabled:opacity-50"
          />
          {selectedFile && (
            <div className="text-xs text-text-muted px-1">
              Selected: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)
            </div>
          )}
        </div>
      )}

      {/* Optional Filename (both modes) */}
      <input
        type="text"
        value={filename}
        onChange={(e) => setFilename(e.target.value)}
        placeholder="Custom filename (optional)"
        disabled={isUploading}
        className="w-full bg-surface-overlay border border-border-subtle rounded px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors disabled:opacity-50"
      />

      {/* Upload Button */}
      <button
        onClick={handleUpload}
        disabled={(mode === 'url' && !url.trim()) || (mode === 'file' && !selectedFile) || isUploading}
        className="w-full py-2 bg-accent/20 text-accent border border-accent/30 rounded text-sm font-medium hover:bg-accent/30 transition-colors disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center gap-2"
      >
        {isUploading ? (
          <>
            <div className="w-3 h-3 border-2 border-accent/50 border-t-accent rounded-full animate-spin" />
            <span>{mode === 'url' ? 'Downloading...' : 'Uploading...'}</span>
          </>
        ) : (
          <>
            <span>{mode === 'url' ? '⬇️' : '⬆️'}</span>
            <span>{mode === 'url' ? 'Download to Workspace' : 'Upload to Workspace'}</span>
          </>
        )}
      </button>

      {/* Result Display */}
      {result && (
        <div
          className={`text-xs p-2 rounded border ${
            result.success
              ? 'bg-status-success/10 border-status-success/30 text-status-success'
              : 'bg-status-error/10 border-status-error/30 text-status-error'
          }`}
        >
          {result.success ? (
            <div className="space-y-1">
              <div className="font-medium">✓ {result.path}</div>
              <div className="text-text-muted">
                {result.type} • {result.size}
              </div>
            </div>
          ) : (
            <div>✗ {result.error}</div>
          )}
        </div>
      )}
    </div>
  );
}
