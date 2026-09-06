// lib/storage.js
// Local persistence, so a reload does not throw away a pipeline.
//
// Every call is guarded: localStorage throws in private browsing modes and
// when a site's data is blocked, and a canvas that cannot autosave should
// still be a canvas the user can draw on.
// --------------------------------------------------

import { fromDocument, toDocument } from './serialize';

const KEY = 'node-pipeline-designer:pipeline';

const available = () => {
  try {
    const probe = '__npd_probe__';
    window.localStorage.setItem(probe, '1');
    window.localStorage.removeItem(probe);
    return true;
  } catch (error) {
    return false;
  }
};

export const isStorageAvailable = available;

export const savePipeline = (nodes, edges, meta) => {
  if (!available()) return false;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(toDocument(nodes, edges, meta)));
    return true;
  } catch (error) {
    // Most likely the quota: a very large pipeline is not worth crashing over.
    return false;
  }
};

export const loadPipeline = () => {
  if (!available()) return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? fromDocument(raw) : null;
  } catch (error) {
    // A corrupt or outdated entry should not wedge the app on every load.
    return null;
  }
};

export const clearPipeline = () => {
  if (!available()) return;
  try {
    window.localStorage.removeItem(KEY);
  } catch (error) {
    /* nothing useful to do */
  }
};

export const STORAGE_KEY = KEY;
