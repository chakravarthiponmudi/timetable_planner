
import React from 'react';

const TimetableResult = ({ timetables, calendar }) => {
  if (!timetables || timetables.length === 0) {
    return null;
  }

  const days = calendar.days;
  const periods = calendar.periods;

  return (
    <div className="space-y-8">
      {timetables.map((timetableData) => (
        <div key={timetableData.class_name}>
          <h3 className="text-xl font-bold mb-4">{timetableData.class_name}</h3>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse border border-gray-300">
              <thead>
                <tr className="bg-gray-100">
                  <th className="border border-gray-300 p-2">Day/Period</th>
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
                      const periodData = timetableData.timetable[day]?.[period];
                      return (
                        <td key={period} className={`border border-gray-300 p-2 text-center ${periodData?.type === 'free' ? 'bg-gray-50' : ''}`}>
                          {periodData ? (
                            periodData.type === 'free' ? (
                              <span className="text-gray-400">Free</span>
                            ) : periodData.type === 'blocked' ? (
                                <div className='p-1'>
                                    <span className="font-semibold">{periodData.subject}</span>
                                    <br />
                                    <span className="text-xs text-gray-500">(Blocked)</span>
                                </div>
                            ) : (
                              <div>
                                <span className="font-semibold">{periodData.subject}</span>
                                <br />
                                <span className="text-xs text-gray-500">{periodData.teacher}</span>
                              </div>
                            )
                          ) : null}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
};

export default TimetableResult;
