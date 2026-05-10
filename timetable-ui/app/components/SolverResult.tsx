
import React from 'react';
import TimetableResult from './TimetableResult';
import TeacherAllocationResult from './TeacherAllocationResult';
import { pdf } from '@react-pdf/renderer';
import TimetablePDF from './TimetablePDF';
import { SolverResult as SolverResultType, Calendar } from '../types';

interface SolverResultProps {
  result: SolverResultType | null;
  calendar: Calendar;
}

const SolverResult = ({ result, calendar }: SolverResultProps) => {
  if (!result) {
    return null;
  }

  const handleExportPdf = async () => {
    try {
      const blob = await pdf(<TimetablePDF result={result} calendar={calendar} />).toBlob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `timetable_${new Date().toISOString().split('T')[0]}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to export PDF:', error);
      alert('Failed to generate PDF. Please try again.');
    }
  };
  
  return (
    <div className="space-y-6">
       <div className="flex justify-end">
        <button
          onClick={handleExportPdf}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded shadow transition-colors"
        >
          Export as PDF (High Quality)
        </button>
      </div>
      <div className="p-4 bg-white">
        {result.payload?.timetables && (
          <TimetableResult timetables={result.payload.timetables} calendar={calendar} />
        )}
        {result.payload?.teacher_allocations && (
          <div className="mt-8">
            <TeacherAllocationResult teacherAllocations={result.payload.teacher_allocations} calendar={calendar} />
          </div>
        )}
      </div>
    </div>
  );
};

export default SolverResult;
