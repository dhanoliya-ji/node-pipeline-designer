// NodeField.js
// Renders a single control from its declarative field spec.
// Adding a new input type to the whole app means adding one case here.
// --------------------------------------------------

import { AutosizeTextarea } from './AutosizeTextarea';

export const NodeField = ({ field, value, onChange }) => {
  const { name, label, type = 'text', placeholder, options = [], hint } = field;
  const controlId = `${field.nodeId}-${name}`;

  const control = () => {
    switch (type) {
      case 'select':
        return (
          <select
            id={controlId}
            className="node-control"
            value={value}
            onChange={(e) => onChange(e.target.value)}
          >
            {options.map((option) => {
              const opt =
                typeof option === 'string' ? { value: option, label: option } : option;
              return (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              );
            })}
          </select>
        );

      case 'number':
        return (
          <input
            id={controlId}
            className="node-control"
            type="number"
            value={value}
            min={field.min}
            max={field.max}
            step={field.step}
            placeholder={placeholder}
            onChange={(e) => onChange(e.target.value)}
          />
        );

      case 'checkbox':
        return (
          <label className="node-checkbox">
            <input
              id={controlId}
              type="checkbox"
              checked={Boolean(value)}
              onChange={(e) => onChange(e.target.checked)}
            />
            <span>{field.checkboxLabel || label}</span>
          </label>
        );

      case 'slider':
        return (
          <div className="node-slider">
            <input
              id={controlId}
              type="range"
              value={value}
              min={field.min ?? 0}
              max={field.max ?? 1}
              step={field.step ?? 0.1}
              onChange={(e) => onChange(Number(e.target.value))}
            />
            <span className="node-slider__value">{value}</span>
          </div>
        );

      case 'textarea':
        return (
          <AutosizeTextarea
            id={controlId}
            value={value}
            placeholder={placeholder}
            minRows={field.minRows}
            maxRows={field.maxRows}
            monospace={field.monospace}
            onChange={onChange}
          />
        );

      case 'readonly':
        return <div className="node-readonly">{value || placeholder}</div>;

      case 'text':
      default:
        return (
          <input
            id={controlId}
            className="node-control"
            type="text"
            value={value}
            placeholder={placeholder}
            onChange={(e) => onChange(e.target.value)}
          />
        );
    }
  };

  // A checkbox carries its own inline label, so it skips the stacked layout.
  if (type === 'checkbox') {
    return <div className="node-field">{control()}</div>;
  }

  return (
    <div className="node-field">
      {label && (
        <label className="node-field__label" htmlFor={controlId}>
          {label}
        </label>
      )}
      {control()}
      {hint && <p className="node-field__hint">{hint}</p>}
    </div>
  );
};
