
import React, { useRef } from 'react';
import TimetableResult from './TimetableResult';
import TeacherAllocationResult from './TeacherAllocationResult';
// Note: jspdf and html2canvas are required for PDF export.
// Make sure to install them: npm install jspdf html2canvas
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas-pro';
import { SolverResult as SolverResultType, Calendar } from '../types';

interface SolverResultProps {
  result: SolverResultType | null;
  calendar: Calendar;
}

const SolverResult = ({ result, calendar }: SolverResultProps) => {
  const contentRef = useRef(null);

  if (!result) {
    return null;
  }

  const handleExportPdf = () => {
    if (!contentRef.current) return;

    // Temporarily increase resolution for better quality
    const scale = 2;
    html2canvas(contentRef.current, { scale: scale }).then((canvas) => {
      const imgData = canvas.toDataURL('image/png');
      const pdf = new jsPDF('p', 'mm', 'a4');
      const pdfWidth = pdf.internal.pageSize.getWidth();
      const pdfHeight = pdf.internal.pageSize.getHeight();
      const canvasWidth = canvas.width;
      const canvasHeight = canvas.height;
      const ratio = canvasWidth / canvasHeight;
      const width = pdfWidth;
      const height = width / ratio;

      let position = 0;
      let heightLeft = height;

      pdf.addImage(imgData, 'PNG', 0, position, width, height);
      heightLeft -= pdfHeight;

      while (heightLeft > 0) {
        position = heightLeft - height;
        pdf.addPage();
        pdf.addImage(imgData, 'PNG', 0, position, width, height);
        heightLeft -= pdfHeight;
      }

      pdf.save('timetable.pdf');
    });
  };
  
  return (
    <div className="space-y-6">
       <div className="flex justify-end">
        <button
          onClick={handleExportPdf}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded shadow"
        >
          Export as PDF
        </button>
      </div>
      <div ref={contentRef} className="p-4 bg-white">
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
