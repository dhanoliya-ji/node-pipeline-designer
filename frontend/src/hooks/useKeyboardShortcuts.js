// hooks/useKeyboardShortcuts.js
// Canvas-wide keyboard shortcuts.
//
// A single listener on the document rather than one per component, so the
// bindings live in one readable table and cannot drift apart.
// --------------------------------------------------

import { useEffect } from 'react';

// Anything typed into a form control belongs to that control. Without this
// check, deleting a character in a Text node would delete the node.
const isTyping = (target) => {
  if (!target) return false;
  const tag = target.tagName;
  return (
    tag === 'INPUT' ||
    tag === 'TEXTAREA' ||
    tag === 'SELECT' ||
    target.isContentEditable
  );
};

export const SHORTCUTS = [
  { keys: 'Ctrl / Cmd + Z', label: 'Undo' },
  { keys: 'Ctrl / Cmd + Shift + Z', label: 'Redo' },
  { keys: 'Ctrl / Cmd + S', label: 'Save to browser' },
  { keys: 'Ctrl / Cmd + D', label: 'Duplicate selection' },
  { keys: 'Ctrl / Cmd + Enter', label: 'Run pipeline' },
  { keys: 'Ctrl / Cmd + L', label: 'Auto-layout' },
  { keys: 'Delete / Backspace', label: 'Delete selection' },
];

export const useKeyboardShortcuts = (handlers) => {
  useEffect(() => {
    const onKeyDown = (event) => {
      const modifier = event.ctrlKey || event.metaKey;
      const key = event.key.toLowerCase();

      // React Flow already removes the selection on Delete; the guard here
      // only stops that happening while a field has focus.
      if (!modifier && (key === 'delete' || key === 'backspace')) {
        if (isTyping(event.target)) return;
        event.preventDefault();
        handlers.onDelete?.();
        return;
      }

      if (!modifier) return;

      switch (key) {
        case 'z':
          event.preventDefault();
          if (event.shiftKey) handlers.onRedo?.();
          else handlers.onUndo?.();
          break;
        case 'y': // Windows convention for redo.
          event.preventDefault();
          handlers.onRedo?.();
          break;
        case 's':
          event.preventDefault();
          handlers.onSave?.();
          break;
        case 'd':
          if (isTyping(event.target)) return;
          event.preventDefault();
          handlers.onDuplicate?.();
          break;
        case 'l':
          event.preventDefault();
          handlers.onLayout?.();
          break;
        case 'enter':
          event.preventDefault();
          handlers.onRun?.();
          break;
        default:
          break;
      }
    };

    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [handlers]);
};
