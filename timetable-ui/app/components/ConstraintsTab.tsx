import React from 'react';
import { TimetableInput } from '../types';

interface Props {
  data: TimetableInput;
  onChange: (data: TimetableInput) => void;
  overrideClass: string;
  setOverrideClass: (val: string) => void;
  overrideVal: number;
  setOverrideVal: (val: number) => void;
  tagName: string;
  setTagName: (val: string) => void;
  tagLimit: number;
  setTagLimit: (val: number) => void;
}

export default function ConstraintsTab({ 
  data, 
  onChange,
  overrideClass,
  setOverrideClass,
  overrideVal,
  setOverrideVal,
  tagName,
  setTagName,
  tagLimit,
  setTagLimit,
}: Props) {
  const constraints = data.constraints;

  const updateConstraints = (updates: Partial<typeof constraints>) => {
    onChange({ ...data, constraints: { ...constraints, ...updates } });
  };

  return (
    <div className="space-y-8 p-4 border rounded bg-white">
      <h2 className="text-xl font-bold">Constraints</h2>

      {/* Min Classes Per Week */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div className="space-y-2">
          <label className="block font-medium">Global Min Classes Per Week</label>
          <div className="flex gap-2">
            <input
              type="number"
              className="border p-2 rounded w-24"
              value={constraints.min_classes_per_week ?? 0}
              onChange={(e) => updateConstraints({ min_classes_per_week: parseInt(e.target.value) || 0 })}
            />
            <button onClick={() => updateConstraints({ min_classes_per_week: undefined })} className="text-red-600 text-sm hover:underline">Clear</button>
          </div>
        </div>

        <div className="space-y-2">
          <label className="block font-medium">Per-class Override</label>
          <div className="flex gap-2">
            <select className="border p-2 rounded" value={overrideClass} onChange={e => setOverrideClass(e.target.value)}>
              <option value="">(select class)</option>
              {data.classes.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
            </select>
            <input type="number" className="border p-2 rounded w-20" value={overrideVal} onChange={e => setOverrideVal(parseInt(e.target.value) || 0)} />
            <button
              onClick={() => {
                if (!overrideClass) return;
                const next = { ...(constraints.min_classes_per_week_by_class || {}) };
                next[overrideClass] = overrideVal;
                updateConstraints({ min_classes_per_week_by_class: next });
              }}
              className="bg-gray-200 px-3 py-2 rounded hover:bg-gray-300"
            >Apply</button>
          </div>
          {constraints.min_classes_per_week_by_class && Object.keys(constraints.min_classes_per_week_by_class).length > 0 && (
            <div className="text-sm text-gray-600 mt-2">
              Overrides: {Object.entries(constraints.min_classes_per_week_by_class).map(([k, v]) => `${k}=${v}`).join(', ')}
            </div>
          )}
        </div>
      </div>

      <hr />

      {/* Teacher Max Periods */}
      <div className="space-y-2">
        <label className="block font-medium">Global Teacher Max Periods/Week</label>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={constraints.teacher_max_periods_per_week !== undefined && constraints.teacher_max_periods_per_week !== null}
              onChange={(e) => updateConstraints({ teacher_max_periods_per_week: e.target.checked ? 16 : null })}
            />
            Enable
          </label>
          {constraints.teacher_max_periods_per_week != null && (
            <input
              type="number"
              className="border p-2 rounded w-24"
              value={constraints.teacher_max_periods_per_week}
              onChange={(e) => updateConstraints({ teacher_max_periods_per_week: parseInt(e.target.value) || 0 })}
            />
          )}
        </div>
      </div>

      <hr />

      {/* Tag Limits */}
      <div className="space-y-4">
        <label className="block font-medium">Max Periods Per Day by Tag</label>
        <div className="flex gap-2 items-end">
          <div>
            <span className="text-xs text-gray-500 block">Tag</span>
            <input type="text" className="border p-2 rounded" value={tagName} onChange={e => setTagName(e.target.value)} />
          </div>
          <div>
            <span className="text-xs text-gray-500 block">Max/Day</span>
            <input type="number" className="border p-2 rounded w-20" value={tagLimit} onChange={e => setTagLimit(parseInt(e.target.value) || 0)} />
          </div>
          <button
            onClick={() => {
              if (!tagName) return;
              const next = { ...(constraints.max_periods_per_day_by_tag || {}) };
              next[tagName] = tagLimit;
              updateConstraints({ max_periods_per_day_by_tag: next });
            }}
            className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
          >Add/Update</button>
        </div>
        <div className="border rounded overflow-hidden">
          <table className="w-full text-sm text-left">
            <thead className="bg-gray-50"><tr><th className="p-2">Tag</th><th className="p-2">Max/Day</th><th className="p-2">Action</th></tr></thead>
            <tbody>
              {Object.entries(constraints.max_periods_per_day_by_tag || {}).map(([tag, limit]) => (
                <tr key={tag} className="border-t">
                  <td className="p-2">{tag}</td>
                  <td className="p-2">{limit}</td>
                  <td className="p-2">
                    <button
                      onClick={() => {
                        const next = { ...constraints.max_periods_per_day_by_tag };
                        delete next[tag];
                        updateConstraints({ max_periods_per_day_by_tag: next });
                      }}
                      className="text-red-600 hover:underline"
                    >Remove</button>
                  </td>
                </tr>
              ))}
              {Object.keys(constraints.max_periods_per_day_by_tag || {}).length === 0 && (
                <tr><td colSpan={3} className="p-4 text-center text-gray-500">No tag limits defined.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}