import React from 'react';
import { TimetableInput, TeacherConfig } from '../types';

interface Props {
  data: TimetableInput;
  onChange: (data: TimetableInput) => void;
  selectedTeacherName: string;
  setSelectedTeacherName: (name: string) => void;
  newTeacherName: string;
  setNewTeacherName: (name: string) => void;
}

export default function TeachersTab({ 
  data, 
  onChange,
  selectedTeacherName,
  setSelectedTeacherName,
  newTeacherName,
  setNewTeacherName,
}: Props) {

  const selectedTeacher = data.teachers.find(t => t.name === selectedTeacherName);

  const addTeacher = () => {
    if (!newTeacherName.trim()) return;
    if (data.teachers.some(t => t.name === newTeacherName)) return alert("Teacher exists");
    const newT: TeacherConfig = { name: newTeacherName, unavailable_periods: [], preferred_periods: [] };
    onChange({ ...data, teachers: [...data.teachers, newT] });
    setNewTeacherName("");
    setSelectedTeacherName(newT.name);
  };

  const removeTeacher = () => {
    if (!selectedTeacherName) return;
    if (!confirm(`Delete teacher ${selectedTeacherName}?`)) return;
    onChange({ ...data, teachers: data.teachers.filter(t => t.name !== selectedTeacherName) });
    setSelectedTeacherName("");
  };

  const updateSelectedTeacher = (updates: Partial<TeacherConfig>) => {
    onChange({
      ...data,
      teachers: data.teachers.map(t => t.name === selectedTeacherName ? { ...t, ...updates } : t)
    });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-8 p-4 border rounded bg-white">
      {/* Left Column: List & Add */}
      <div className="space-y-6">
        <div className="space-y-2">
          <label className="block font-medium">Select Teacher</label>
          <select
            className="w-full border p-2 rounded"
            value={selectedTeacherName}
            onChange={e => setSelectedTeacherName(e.target.value)}
          >
            <option value="">(none)</option>
            {data.teachers.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
          </select>
        </div>

        <div className="space-y-2 border-t pt-4">
          <label className="block font-medium">Add Teacher</label>
          <div className="flex gap-2">
            <input
              type="text"
              className="w-full border p-2 rounded"
              placeholder="Name"
              value={newTeacherName}
              onChange={e => setNewTeacherName(e.target.value)}
            />
            <button onClick={addTeacher} className="bg-green-600 text-white px-3 py-2 rounded hover:bg-green-700">Add</button>
          </div>
        </div>

        {selectedTeacherName && (
          <button onClick={removeTeacher} className="w-full border border-red-300 text-red-600 px-4 py-2 rounded hover:bg-red-50">
            Remove Selected
          </button>
        )}
      </div>

      {/* Right Column: Edit Details */}
      <div className="md:col-span-2 space-y-6">
        {!selectedTeacher ? (
          <div className="text-gray-500 italic">Select a teacher to edit constraints.</div>
        ) : (
          <>
            <h3 className="text-lg font-bold border-b pb-2">Editing: {selectedTeacher.name}</h3>

            <div className="space-y-2">
              <label className="flex items-center gap-2 font-medium">
                <input
                  type="checkbox"
                  checked={selectedTeacher.max_periods_per_week != null}
                  onChange={e => updateSelectedTeacher({ max_periods_per_week: e.target.checked ? 10 : null })}
                />
                Max Periods Per Week
              </label>
              {selectedTeacher.max_periods_per_week != null && (
                <input
                  type="number"
                  className="border p-2 rounded w-24 ml-6"
                  value={selectedTeacher.max_periods_per_week}
                  onChange={e => updateSelectedTeacher({ max_periods_per_week: parseInt(e.target.value) || 0 })}
                />
              )}
            </div>

            <div className="space-y-2">
              <label className="block font-medium">Preferred Periods (Soft Preference)</label>
              <div className="flex flex-wrap gap-2">
                {data.calendar.periods.map(p => {
                  const isPref = selectedTeacher.preferred_periods.includes(p);
                  return (
                    <button
                      key={p}
                      onClick={() => {
                        const newPref = isPref
                          ? selectedTeacher.preferred_periods.filter(x => x !== p)
                          : [...selectedTeacher.preferred_periods, p];
                        updateSelectedTeacher({ preferred_periods: newPref });
                      }}
                      className={`px-3 py-1 rounded border text-sm ${isPref ? 'bg-blue-100 border-blue-400 text-blue-800' : 'bg-gray-50 border-gray-200'}`}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="space-y-2">
              <label className="block font-medium">Unavailable Periods (Hard Constraint)</label>
              <div className="border rounded p-2 max-h-60 overflow-y-auto bg-gray-50">
                {data.calendar.days.map(d => (
                  <div key={d} className="flex items-center gap-2 mb-1">
                    <span className="w-12 font-bold text-xs text-gray-500">{d}</span>
                    {data.calendar.periods.map(p => {
                      const isUnavail = selectedTeacher.unavailable_periods.some(up => up.day === d && up.period === p);
                      return (
                        <button
                          key={p}
                          onClick={() => {
                            const newUnavail = isUnavail
                              ? selectedTeacher.unavailable_periods.filter(up => !(up.day === d && up.period === p))
                              : [...selectedTeacher.unavailable_periods, { day: d, period: p }];
                            updateSelectedTeacher({ unavailable_periods: newUnavail });
                          }}
                          className={`w-10 h-8 text-xs rounded border ${isUnavail ? 'bg-red-100 border-red-400 text-red-800' : 'bg-white border-gray-300'}`}
                          title={`${d} ${p}`}
                        >
                          {p}
                        </button>
                      );
                    })}
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}