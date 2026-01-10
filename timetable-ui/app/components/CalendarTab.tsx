import React from 'react';
import { TimetableInput } from '../types';

interface Props {
  data: TimetableInput;
  onChange: (data: TimetableInput) => void;
  days: string;
  setDays: (days: string) => void;
  periods: string;
  setPeriods: (periods: string) => void;
}

export default function CalendarTab({ data, onChange, days, setDays, periods, setPeriods }: Props) {

  const handleApply = () => {
    const newDays = days.split(',').map(s => s.trim()).filter(Boolean);
    const newPeriods = periods.split(',').map(s => s.trim()).filter(Boolean);
    onChange({
      ...data,
      calendar: { days: newDays, periods: newPeriods }
    });
  };

  return (
    <div className="space-y-6 p-4 border rounded bg-white">
      <h2 className="text-xl font-bold">Calendar</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <label className="block text-sm font-medium mb-1">Days (comma-separated)</label>
          <input type="text" className="w-full border p-2 rounded" value={days} onChange={e => setDays(e.target.value)} />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Periods (comma-separated)</label>
          <input type="text" className="w-full border p-2 rounded" value={periods} onChange={e => setPeriods(e.target.value)} />
        </div>
      </div>
      <button onClick={handleApply} className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">Apply calendar changes</button>
    </div>
  );
}