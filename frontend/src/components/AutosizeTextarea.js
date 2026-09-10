// AutosizeTextarea.js
// A textarea that grows in both axes to fit its content.
// Width follows the longest line (in `ch` units); height is measured from
// scrollHeight so wrapped lines are counted correctly. Both are clamped.
// --------------------------------------------------

import { useRef, useLayoutEffect, useMemo } from 'react';

const MIN_COLS = 22;
const MAX_COLS = 60;

export const AutosizeTextarea = ({
  id,
  value = '',
  placeholder,
  minRows = 2,
  maxRows = 14,
  monospace = false,
  onChange,
}) => {
  const ref = useRef(null);

  const cols = useMemo(() => {
    const longest = String(value)
      .split('\n')
      .reduce((max, line) => Math.max(max, line.length), 0);
    return Math.min(MAX_COLS, Math.max(MIN_COLS, longest + 2));
  }, [value]);

  // Height has to be measured after the width change lands, otherwise
  // scrollHeight reflects the previous wrap.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;

    const style = window.getComputedStyle(el);
    const lineHeight = parseFloat(style.lineHeight) || 18;
    const padding =
      parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);

    el.style.height = 'auto';
    const contentHeight = el.scrollHeight - padding;
    const rows = Math.min(
      maxRows,
      Math.max(minRows, Math.ceil(contentHeight / lineHeight))
    );
    el.style.height = `${rows * lineHeight + padding}px`;
    el.style.overflowY = rows >= maxRows ? 'auto' : 'hidden';
  }, [value, cols, minRows, maxRows]);

  return (
    <textarea
      id={id}
      ref={ref}
      className={`node-control node-control--textarea${
        monospace ? ' node-control--mono' : ''
      }`}
      style={{ width: `${cols}ch` }}
      value={value}
      placeholder={placeholder}
      spellCheck={false}
      onChange={(e) => onChange(e.target.value)}
    />
  );
};
