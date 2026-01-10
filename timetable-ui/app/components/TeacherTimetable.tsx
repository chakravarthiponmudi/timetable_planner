import React from 'react';

const TeacherTimetable = ({ teacherTimetable, calendar }) => {
  if (!teacherTimetable) {
    return null;
  }

  const days = calendar.days;
  const periods = calendar.periods;

  return (
    <div className="mb-8">
      <h4 className="text-lg font-bold mb-2">{teacherTimetable.teacher_name} - Total Periods: {teacherTimetable.total_periods}</h4>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse border border-gray-300">
          <thead className="bg-gray-100">
            <tr>
              <th className="border border-gray-300 p-2">Day</th>
              {periods.map((period) => (
                <th key={period} className="border border-gray-300 p-2">{period}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {days.map((day) => (
              <tr key={day}>
                <td className="border border-gray-300 p-2 font-medium">{day}</td>
                {periods.map((period) => {
                  const cell = teacherTimetable.timetable[day][period];
                  let cellContent = '';
                  if (cell.type === 'class') {
                    cellContent = `${cell.class}: ${cell.subject}`;
                  }
                  return (
                    <td key={period} className="border border-gray-300 p-2">
                      {cellContent}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default TeacherTimetable;