import React, { useState } from 'react';
import { TimetableInput, ClassConfig, Subject, Semester } from '../types';

interface Props {
  data: TimetableInput;
  onChange: (data: TimetableInput) => void;
}

const SEMESTERS = ["S1", "S2"];

export default function ClassesTab({ data, onChange }: Props) {
  const [selectedClassName, setSelectedClassName] = useState("");
  const [newClassName, setNewClassName] = useState("");
  const [selectedSem, setSelectedSem] = useState("S1");
  
  // Subject Editing State
  const [editingSubjectIndex, setEditingSubjectIndex] = useState<number | null>(null); // null = adding new
  const [subjectForm, setSubjectForm] = useState<Partial<Subject>>({});

  const selectedClass = data.classes.find(c => c.name === selectedClassName);
  const selectedSemesterData = selectedClass?.semesters[selectedSem];

  const addClass = () => {
    if (!newClassName.trim()) return;
    if (data.classes.some(c => c.name === newClassName)) return alert("Class exists");
    const newC: ClassConfig = { name: newClassName, semesters: { "S1": { subjects: [], blocked_periods: [] } } };
    onChange({ ...data, classes: [...data.classes, newC] });
    setNewClassName("");
    setSelectedClassName(newC.name);
  };

  const updateClass = (updates: Partial<ClassConfig>) => {
    onChange({
      ...data,
      classes: data.classes.map(c => c.name === selectedClassName ? { ...c, ...updates } : c)
    });
  };

  const toggleSemester = (sem: string) => {
    if (!selectedClass) return;
    const newSems = { ...selectedClass.semesters };
    if (newSems[sem]) {
      delete newSems[sem];
    } else {
      newSems[sem] = { subjects: [], blocked_periods: [] };
    }
    updateClass({ semesters: newSems });
  };

  const saveSubject = () => {
    if (!selectedClass || !selectedSemesterData) return;
    if (!subjectForm.name || !subjectForm.teachers?.length) return alert("Name and Teacher required");

    const newSubj = {
      name: subjectForm.name,
      teachers: subjectForm.teachers,
      teaching_mode: subjectForm.teaching_mode || "any_of",
      periods_per_week: subjectForm.periods_per_week || 1,
      min_contiguous_periods: subjectForm.min_contiguous_periods || 1,
      max_contiguous_periods: subjectForm.max_contiguous_periods || 1,
      tags: subjectForm.tags || [],
      allowed_starts: subjectForm.allowed_starts || [],
      fixed_sessions: subjectForm.fixed_sessions || [],
      teacher_share_min_percent: subjectForm.teacher_share_min_percent || {},
    } as Subject;

    const newSubjects = [...selectedSemesterData.subjects];
    if (editingSubjectIndex !== null && editingSubjectIndex >= 0) {
      newSubjects[editingSubjectIndex] = newSubj;
    } else {
      newSubjects.push(newSubj);
    }

    const newSems = { ...selectedClass.semesters };
    newSems[selectedSem] = { ...selectedSemesterData, subjects: newSubjects };
    updateClass({ semesters: newSems });
    
    // Reset form
    setEditingSubjectIndex(null);
    setSubjectForm({});
  };

  const deleteSubject = (idx: number) => {
    if (!selectedClass || !selectedSemesterData) return;
    if (!confirm("Delete subject?")) return;
    const newSubjects = selectedSemesterData.subjects.filter((_, i) => i !== idx);
    const newSems = { ...selectedClass.semesters };
    newSems[selectedSem] = { ...selectedSemesterData, subjects: newSubjects };
    updateClass({ semesters: newSems });
  };

  const editSubject = (idx: number) => {
    if (!selectedSemesterData) return;
    setEditingSubjectIndex(idx);
    setSubjectForm({ ...selectedSemesterData.subjects[idx] });
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 p-4 border rounded bg-white">
      {/* Sidebar: Class List */}
      <div className="lg:col-span-1 space-y-6 border-r pr-4">
        <div className="space-y-2">
          <label className="block font-medium">Select Class</label>
          <select className="w-full border p-2 rounded" value={selectedClassName} onChange={e => setSelectedClassName(e.target.value)}>
            <option value="">(none)</option>
            {data.classes.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>
        </div>
        <div className="space-y-2">
          <label className="block font-medium">Add Class</label>
          <div className="flex gap-2">
            <input type="text" className="w-full border p-2 rounded" placeholder="Name" value={newClassName} onChange={e => setNewClassName(e.target.value)} />
            <button onClick={addClass} className="bg-green-600 text-white px-3 py-2 rounded">Add</button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="lg:col-span-3 space-y-6">
        {!selectedClass ? (
          <div className="text-gray-500 italic">Select a class to manage subjects.</div>
        ) : (
          <>
            <div className="flex items-center justify-between border-b pb-2">
              <h2 className="text-xl font-bold">{selectedClass.name}</h2>
              <div className="flex gap-4">
                {SEMESTERS.map(sem => (
                  <label key={sem} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={!!selectedClass.semesters[sem]}
                      onChange={() => toggleSemester(sem)}
                    />
                    Enable {sem}
                  </label>
                ))}
              </div>
            </div>

            {/* Semester Tabs */}
            <div className="flex gap-2 border-b">
              {SEMESTERS.filter(s => selectedClass.semesters[s]).map(sem => (
                <button
                  key={sem}
                  onClick={() => setSelectedSem(sem)}
                  className={`px-4 py-2 ${selectedSem === sem ? 'border-b-2 border-blue-600 font-bold' : 'text-gray-500'}`}
                >
                  {sem}
                </button>
              ))}
            </div>

            {!selectedSemesterData ? (
              <div className="p-4 bg-yellow-50 text-yellow-800 rounded">Semester {selectedSem} is not enabled for this class.</div>
            ) : (
              <div className="space-y-8">
                {/* Subjects List */}
                <div>
                  <h3 className="font-bold mb-2">Subjects</h3>
                  <div className="overflow-x-auto border rounded">
                    <table className="w-full text-sm text-left">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="p-2">Name</th>
                          <th className="p-2">Teachers</th>
                          <th className="p-2">Periods</th>
                          <th className="p-2">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedSemesterData.subjects.map((subj, idx) => (
                          <tr key={idx} className="border-t hover:bg-gray-50">
                            <td className="p-2 font-medium">{subj.name}</td>
                            <td className="p-2">{subj.teachers.join(', ')}</td>
                            <td className="p-2">{subj.periods_per_week}</td>
                            <td className="p-2 flex gap-2">
                              <button onClick={() => editSubject(idx)} className="text-blue-600 hover:underline">Edit</button>
                              <button onClick={() => deleteSubject(idx)} className="text-red-600 hover:underline">Delete</button>
                            </td>
                          </tr>
                        ))}
                        {selectedSemesterData.subjects.length === 0 && (
                          <tr><td colSpan={4} className="p-4 text-center text-gray-500">No subjects.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Add/Edit Subject Form */}
                <div className="border p-4 rounded bg-gray-50 space-y-4">
                  <h3 className="font-bold text-lg">{editingSubjectIndex !== null ? "Edit Subject" : "Add New Subject"}</h3>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-bold uppercase text-gray-500">Name</label>
                      <input
                        className="w-full border p-2 rounded"
                        value={subjectForm.name || ""}
                        onChange={e => setSubjectForm({ ...subjectForm, name: e.target.value })}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold uppercase text-gray-500">Teachers</label>
                      <select
                        multiple
                        className="w-full border p-2 rounded h-24"
                        value={subjectForm.teachers || []}
                        onChange={e => {
                          const selected = Array.from(e.target.selectedOptions, option => option.value);
                          setSubjectForm({ ...subjectForm, teachers: selected });
                        }}
                      >
                        {data.teachers.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
                      </select>
                      <p className="text-xs text-gray-500 mt-1">Hold Ctrl/Cmd to select multiple.</p>
                    </div>
                    
                    <div>
                      <label className="block text-xs font-bold uppercase text-gray-500">Periods / Week</label>
                      <input
                        type="number"
                        className="w-full border p-2 rounded"
                        value={subjectForm.periods_per_week || 1}
                        onChange={e => setSubjectForm({ ...subjectForm, periods_per_week: parseInt(e.target.value) || 1 })}
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-bold uppercase text-gray-500">Teaching Mode</label>
                      <select
                        className="w-full border p-2 rounded"
                        value={subjectForm.teaching_mode || "any_of"}
                        onChange={e => setSubjectForm({ ...subjectForm, teaching_mode: e.target.value as any })}
                      >
                        <option value="any_of">any_of (OR)</option>
                        <option value="all_of">all_of (AND)</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-bold uppercase text-gray-500">Min Contiguous</label>
                      <input
                        type="number"
                        className="w-full border p-2 rounded"
                        value={subjectForm.min_contiguous_periods || 1}
                        onChange={e => setSubjectForm({ ...subjectForm, min_contiguous_periods: parseInt(e.target.value) || 1 })}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold uppercase text-gray-500">Max Contiguous</label>
                      <input
                        type="number"
                        className="w-full border p-2 rounded"
                        value={subjectForm.max_contiguous_periods || 1}
                        onChange={e => setSubjectForm({ ...subjectForm, max_contiguous_periods: parseInt(e.target.value) || 1 })}
                      />
                    </div>
                  </div>

                  {/* Advanced fields like Fixed Sessions could go here, simplified for this view */}
                  
                  <div className="flex gap-2 pt-2">
                    <button onClick={saveSubject} className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
                      {editingSubjectIndex !== null ? "Update Subject" : "Add Subject"}
                    </button>
                    {editingSubjectIndex !== null && (
                      <button
                        onClick={() => { setEditingSubjectIndex(null); setSubjectForm({}); }}
                        className="bg-gray-200 text-gray-800 px-4 py-2 rounded hover:bg-gray-300"
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </div>

                {/* Blocked Periods for Class/Semester */}
                <div className="border-t pt-4">
                  <h3 className="font-bold mb-2">Blocked Periods</h3>
                  <div className="flex flex-wrap gap-2">
                    {data.calendar.days.map(d => (
                      <div key={d} className="flex flex-col gap-1 border p-2 rounded">
                        <span className="text-xs font-bold text-center">{d}</span>
                        {data.calendar.periods.map(p => {
                          const isBlocked = selectedSemesterData.blocked_periods.some(bp => bp.day === d && bp.period === p);
                          return (
                            <button
                              key={p}
                              onClick={() => {
                                const newBlocked = isBlocked
                                  ? selectedSemesterData.blocked_periods.filter(bp => !(bp.day === d && bp.period === p))
                                  : [...selectedSemesterData.blocked_periods, { day: d, period: p }];
                                const newSems = { ...selectedClass.semesters };
                                newSems[selectedSem] = { ...selectedSemesterData, blocked_periods: newBlocked };
                                updateClass({ semesters: newSems });
                              }}
                              className={`text-xs px-2 py-1 rounded ${isBlocked ? 'bg-red-500 text-white' : 'bg-gray-100'}`}
                            >{p}</button>
                          );
                        })}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}