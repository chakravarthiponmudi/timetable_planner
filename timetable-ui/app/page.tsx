"use client";

import React, { useState } from 'react';
import { TimetableInput, DEFAULT_DATA } from './types';
import CalendarTab from './components/CalendarTab';
import ConstraintsTab from './components/ConstraintsTab';
import TeachersTab from './components/TeachersTab';
import ClassesTab from './components/ClassesTab';

export default function TimetableEditor() {
  const [data, setData] = useState<TimetableInput>(DEFAULT_DATA);
  const [activeTab, setActiveTab] = useState("calendar");

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const json = JSON.parse(evt.target?.result as string);
        setData(json);
      } catch (err) {
        alert("Invalid JSON file");
      }
    };
    reader.readAsText(file);
  };

  const handleDownload = () => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "timetable_input.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="min-h-screen bg-gray-50 p-8 font-sans text-gray-900">
      <div className="max-w-7xl mx-auto space-y-6">
        <header className="flex justify-between items-center bg-white p-6 rounded shadow-sm">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">Timetable Input Editor</h1>
            <p className="text-gray-500 text-sm">Next.js Port of Streamlit GUI</p>
          </div>
          <div className="flex gap-4">
            <label className="bg-gray-100 hover:bg-gray-200 px-4 py-2 rounded cursor-pointer border">
              Open JSON
              <input type="file" accept=".json" className="hidden" onChange={handleFileUpload} />
            </label>
            <button onClick={handleDownload} className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded shadow">
              Download JSON
            </button>
          </div>
        </header>

        {/* Tabs Navigation */}
        <div className="flex gap-1 border-b border-gray-300">
          {[
            { id: "calendar", label: "Calendar" },
            { id: "constraints", label: "Constraints" },
            { id: "teachers", label: "Teachers" },
            { id: "classes", label: "Classes & Subjects" },
            { id: "preview", label: "Preview JSON" },
            { id: "run", label: "Run Solver" },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-6 py-3 font-medium rounded-t-lg transition-colors ${
                activeTab === tab.id
                  ? "bg-white border border-b-0 border-gray-300 text-blue-600"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <main>
          {activeTab === "calendar" && <CalendarTab data={data} onChange={setData} />}
          {activeTab === "constraints" && <ConstraintsTab data={data} onChange={setData} />}
          {activeTab === "teachers" && <TeachersTab data={data} onChange={setData} />}
          {activeTab === "classes" && <ClassesTab data={data} onChange={setData} />}
          {activeTab === "preview" && (
            <div className="bg-white p-4 rounded border shadow-sm">
              <pre className="text-xs overflow-auto max-h-[600px]">{JSON.stringify(data, null, 2)}</pre>
            </div>
          )}
          {activeTab === "run" && (
            <div className="bg-white p-6 rounded border shadow-sm space-y-6">
              <h2 className="text-xl font-bold">Run Solver</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div>
                  <label className="block font-medium mb-1">Semester</label>
                  <select className="w-full border p-2 rounded"><option>S1</option><option>S2</option></select>
                </div>
                <div>
                  <label className="block font-medium mb-1">Time Limit (s)</label>
                  <input type="number" defaultValue={10} className="w-full border p-2 rounded" />
                </div>
                <div className="flex items-end">
                  <button onClick={() => alert("Backend execution not implemented in UI demo.")} className="w-full bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 font-bold">Run Solver</button>
                </div>
              </div>
              <p className="text-sm text-gray-500">Note: This UI is a frontend-only port. The actual Python solver execution is not connected.</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}