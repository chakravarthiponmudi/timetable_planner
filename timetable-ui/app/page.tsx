"use client";

import React, { useState, useEffect } from 'react';
import { TimetableInput, Subject, SolverResult } from './types';
import CalendarTab from './components/CalendarTab';
import ConstraintsTab from './components/ConstraintsTab';
import TeachersTab from './components/TeachersTab';
import ClassesTab from './components/ClassesTab';
import SolverResultComponent from './components/SolverResult';

export default function TimetableEditor() {

  const [data, setData] = useState<TimetableInput | null>(null);

  const [activeTab, setActiveTab] = useState("calendar");

  const [error, setError] = useState<string | null>(null);



  // === State lifted from child tabs to preserve UI state across tab switches ===



  // ClassesTab state

  const [selectedClassName, setSelectedClassName] = useState("");

  const [selectedSem, setSelectedSem] = useState("S1");

  const [editingBlocked, setEditingBlocked] = useState<{ day: string; period: string }[]>([]);

  const [editingSubjectIndex, setEditingSubjectIndex] = useState<number | null>(null);

  const [subjectForm, setSubjectForm] = useState<Partial<Subject>>({});

  const [newClassName, setNewClassName] = useState("");



  // TeachersTab state

  const [selectedTeacherName, setSelectedTeacherName] = useState<string>("");

  const [newTeacherName, setNewTeacherName] = useState("");



  // ConstraintsTab state

  const [overrideClass, setOverrideClass] = useState("");

  const [overrideVal, setOverrideVal] = useState(0);

  const [tagName, setTagName] = useState("");

  const [tagLimit, setTagLimit] = useState(1);

  

    // CalendarTab state

  

    const [calendarDays, setCalendarDays] = useState<string | null>(null);

  

    const [calendarPeriods, setCalendarPeriods] = useState<string | null>(null);

  

  

  

    // RunSolver state

  

    const [runSemester, setRunSemester] = useState<"S1" | "S2">("S1");

  

    const [runTimeLimit, setRunTimeLimit] = useState(10);

  

    const [solverResult, setSolverResult] = useState<SolverResult | null>(null);

  

    const [isSolving, setIsSolving] = useState(false);

  

  



  useEffect(() => {

    const fetchData = async () => {

      try {

        const apiUrl = process.env.NEXT_PUBLIC_API_URL;

        if (!apiUrl) {

          setError("API URL is not configured. Please set NEXT_PUBLIC_API_URL environment variable.");

          return;

        }

        const response = await fetch(`${apiUrl}/app_initial_data`);

        if (!response.ok) {

          throw new Error(`Failed to fetch data: ${response.statusText}`);

        }

        const jsonData = await response.json();

        setData(jsonData);

        // Initialize calendar form state after data is loaded

        setCalendarDays(jsonData.calendar.days.join(', '));

        setCalendarPeriods(jsonData.calendar.periods.join(', '));

      } catch (err) {

        setError(err instanceof Error ? err.message : "An unknown error occurred");

      }

        };

        fetchData();

      }, []);

    

      const handleRunSolver = async () => {

        if (!data) return;

        setIsSolving(true);

        setSolverResult(null);

        try {

          const apiUrl = process.env.NEXT_PUBLIC_API_URL;

          const response = await fetch(`${apiUrl}/solve/${runSemester}`, {

            method: 'POST',

            headers: {

              'Content-Type': 'application/json',

            },

            body: JSON.stringify(data),

          });

    

          const result = await response.json();

          if (!response.ok) {

            throw new Error(result.detail?.message || `HTTP error! status: ${response.status}`);

          }

          setSolverResult(result);

        } catch (err) {

          setError(err instanceof Error ? err.message : "An unknown error occurred");
          setSolverResult(null);

        } finally {

          setIsSolving(false);

        }

      };

    



  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const json = JSON.parse(evt.target?.result as string);
        setData(json);
        setError(null);
      } catch (err) {
        alert(`Invalid JSON file: ${err}`);
      }
    };
    reader.readAsText(file);
  };

  const handleDownload = () => {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "timetable_input.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  if (error) {
    return (
      <div className="min-h-screen bg-red-50 p-8 flex items-center justify-center">
        <div className="bg-white p-6 rounded shadow-md text-red-700">
          <h2 className="text-xl font-bold mb-4">Error</h2>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen bg-gray-50 p-8 flex items-center justify-center">
        <div className="text-lg font-medium text-gray-600">Loading data...</div>
      </div>
    );
  }

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
          {activeTab === "calendar" && data && (
            <CalendarTab
              data={data}
              onChange={setData}
              days={calendarDays ?? ''}
              setDays={setCalendarDays}
              periods={calendarPeriods ?? ''}
              setPeriods={setCalendarPeriods}
            />
          )}
          {activeTab === "constraints" && data && (
            <ConstraintsTab
              data={data}
              onChange={setData}
              overrideClass={overrideClass}
              setOverrideClass={setOverrideClass}
              overrideVal={overrideVal}
              setOverrideVal={setOverrideVal}
              tagName={tagName}
              setTagName={setTagName}
              tagLimit={tagLimit}
              setTagLimit={setTagLimit}
            />
          )}
          {activeTab === "teachers" && data && (
            <TeachersTab
              data={data}
              onChange={setData}
              selectedTeacherName={selectedTeacherName}
              setSelectedTeacherName={setSelectedTeacherName}
              newTeacherName={newTeacherName}
              setNewTeacherName={setNewTeacherName}
            />
          )}
          {activeTab === "classes" && data && (
            <ClassesTab
              data={data}
              onChange={setData}
              selectedClassName={selectedClassName}
              setSelectedClassName={setSelectedClassName}
              // newClassName={newClassName}
              // setNewClassName={setNewClassName}
              selectedSem={selectedSem}
              setSelectedSem={setSelectedSem}
              editingBlocked={editingBlocked}
              setEditingBlocked={setEditingBlocked}
              editingSubjectIndex={editingSubjectIndex}
              setEditingSubjectIndex={setEditingSubjectIndex}
              subjectForm={subjectForm}
              setSubjectForm={setSubjectForm}
            />
          )}
          {activeTab === "preview" && data && (
            <div className="bg-white p-4 rounded border shadow-sm">
              <pre className="text-xs overflow-auto max-h-[600px]">{JSON.stringify(data, null, 2)}</pre>
            </div>
          )}
          {activeTab === "run" && data && (
            <div className="bg-white p-6 rounded border shadow-sm space-y-6">
              <h2 className="text-xl font-bold">Run Solver</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div>
                  <label className="block font-medium mb-1">Semester</label>
                  <select 
                    className="w-full border p-2 rounded"
                    value={runSemester}
                    onChange={e => setRunSemester(e.target.value as "S1" | "S2")}
                  >
                    <option>S1</option>
                    <option>S2</option>
                  </select>
                </div>
                <div>
                  <label className="block font-medium mb-1">Time Limit (s)</label>
                  <input 
                    type="number"
                    className="w-full border p-2 rounded"
                    value={runTimeLimit}
                    onChange={e => setRunTimeLimit(parseInt(e.target.value) || 0)}
                  />
                </div>
                <div className="flex items-end">
                  <button 
                    onClick={handleRunSolver} 
                    disabled={isSolving}
                    className="w-full bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 font-bold disabled:bg-gray-400"
                  >
                    {isSolving ? "Solving..." : "Run Solver"}
                  </button>
                </div>
              </div>
              
              {/* Solver Results */}
              <div className="border-t pt-4">
                {isSolving && <div className="text-center text-gray-500">Processing... please wait.</div>}
              
                {solverResult && (
                  <SolverResultComponent result={solverResult} calendar={data.calendar} />
                )}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
