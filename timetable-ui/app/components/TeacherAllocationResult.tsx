import React from 'react';
import TeacherTimetable from './TeacherTimetable';

const TeacherAllocationResult = ({ teacherAllocations, calendar }) => {
  if (!teacherAllocations || teacherAllocations.length === 0) {
    return null;
  }

  return (
    <div>
      <h3 className="text-xl font-bold mb-4">Teacher Timetables</h3>
      {teacherAllocations.map((teacherTimetable) => (
        <TeacherTimetable
          key={teacherTimetable.teacher_name}
          teacherTimetable={teacherTimetable}
          calendar={calendar}
        />
      ))}
    </div>
  );
};

export default TeacherAllocationResult;
