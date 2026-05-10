import React from 'react';
import { Page, Text, View, Document, StyleSheet } from '@react-pdf/renderer';
import { SolverResult as SolverResultType, Calendar } from '../types';

const styles = StyleSheet.create({
  page: {
    padding: 30,
    backgroundColor: '#ffffff',
  },
  section: {
    marginBottom: 20,
  },
  title: {
    fontSize: 18,
    marginBottom: 10,
    textAlign: 'center',
    fontWeight: 'bold',
  },
  subtitle: {
    fontSize: 14,
    marginBottom: 8,
    marginTop: 10,
    fontWeight: 'bold',
  },
  table: {
    display: 'flex',
    width: 'auto',
    borderStyle: 'solid',
    borderWidth: 1,
    borderColor: '#bfbfbf',
    marginBottom: 10,
  },
  tableRow: {
    flexDirection: 'row',
  },
  tableColHeader: {
    borderStyle: 'solid',
    borderWidth: 1,
    borderColor: '#bfbfbf',
    backgroundColor: '#f3f4f6',
    padding: 5,
  },
  tableCol: {
    borderStyle: 'solid',
    borderWidth: 1,
    borderColor: '#bfbfbf',
    padding: 5,
    minHeight: 30,
  },
  tableCellHeader: {
    fontSize: 9,
    fontWeight: 'bold',
  },
  tableCell: {
    fontSize: 8,
  },
  freeCell: {
    backgroundColor: '#f9fafb',
  },
  boldText: {
    fontWeight: 'bold',
  },
  smallText: {
    fontSize: 6,
    color: '#6b7280',
    marginTop: 2,
  }
});

interface TimetablePDFProps {
  result: SolverResultType;
  calendar: Calendar;
}

const TimetablePDF = ({ result, calendar }: TimetablePDFProps) => {
  const { timetables, teacher_allocations } = result.payload;
  const { days, periods } = calendar;

  const getColWidth = (isFirst: boolean) => isFirst ? '12%' : `${88 / periods.length}%`;

  return (
    <Document>
      {/* Class Timetables */}
      {timetables && timetables.length > 0 && (
        <Page size="A4" orientation="landscape" style={styles.page}>
          <Text style={styles.title}>Class Timetables</Text>
          {timetables.map((timetableData, index) => (
            <View key={timetableData.class_name} style={styles.section} break={index > 0}>
              <Text style={styles.subtitle}>{timetableData.class_name}</Text>
              <View style={styles.table}>
                <View style={styles.tableRow}>
                  <View style={[styles.tableColHeader, { width: getColWidth(true) }]}>
                    <Text style={styles.tableCellHeader}>Day/Period</Text>
                  </View>
                  {periods.map((period) => (
                    <View key={period} style={[styles.tableColHeader, { width: getColWidth(false) }]}>
                      <Text style={styles.tableCellHeader}>{period}</Text>
                    </View>
                  ))}
                </View>
                {days.map((day) => (
                  <View key={day} style={styles.tableRow}>
                    <View style={[styles.tableCol, { width: getColWidth(true), backgroundColor: '#f9fafb' }]}>
                      <Text style={[styles.tableCell, styles.boldText]}>{day}</Text>
                    </View>
                    {periods.map((period) => {
                      const cell = timetableData.timetable[day]?.[period];
                      const isFree = cell?.type === 'free';
                      return (
                        <View key={period} style={[styles.tableCol, { width: getColWidth(false) }, isFree ? styles.freeCell : {}]}>
                          {cell ? (
                            <>
                              <Text style={[styles.tableCell, styles.boldText]}>
                                {cell.type === 'free' ? 'Free' : cell.subject}
                              </Text>
                              {cell.type === 'blocked' && <Text style={styles.smallText}>(Blocked)</Text>}
                              {cell.teachers_by_section && cell.teachers_by_section.length > 1 ? (
                                cell.teachers_by_section.map((t, idx) => (
                                  <Text key={idx} style={styles.smallText}>S{idx}: {t}</Text>
                                ))
                              ) : (
                                cell.teacher && <Text style={styles.smallText}>{cell.teacher}</Text>
                              )}
                            </>
                          ) : null}
                        </View>
                      );
                    })}
                  </View>
                ))}
              </View>
            </View>
          ))}
          <Text 
            style={{ position: 'absolute', fontSize: 10, bottom: 20, left: 0, right: 0, textAlign: 'center', color: 'grey' }} 
            render={({ pageNumber, totalPages }) => `${pageNumber} / ${totalPages}`} 
            fixed 
          />
        </Page>
      )}

      {/* Teacher Timetables */}
      {teacher_allocations && teacher_allocations.length > 0 && (
        <Page size="A4" orientation="landscape" style={styles.page}>
          <Text style={styles.title}>Teacher Timetables</Text>
          {teacher_allocations.map((teacherData, index) => (
            <View key={teacherData.teacher_name} style={styles.section} break={index > 0}>
              <Text style={styles.subtitle}>{teacherData.teacher_name} - Total Periods: {teacherData.total_periods}</Text>
              <View style={styles.table}>
                <View style={styles.tableRow}>
                  <View style={[styles.tableColHeader, { width: getColWidth(true) }]}>
                    <Text style={styles.tableCellHeader}>Day</Text>
                  </View>
                  {periods.map((period) => (
                    <View key={period} style={[styles.tableColHeader, { width: getColWidth(false) }]}>
                      <Text style={styles.tableCellHeader}>{period}</Text>
                    </View>
                  ))}
                </View>
                {days.map((day) => (
                  <View key={day} style={styles.tableRow}>
                    <View style={[styles.tableCol, { width: getColWidth(true), backgroundColor: '#f9fafb' }]}>
                      <Text style={[styles.tableCell, styles.boldText]}>{day}</Text>
                    </View>
                    {periods.map((period) => {
                      const cell = teacherData.timetable[day]?.[period];
                      let content = '';
                      if (cell?.type === 'class') {
                        content = `${cell.class}: ${cell.subject}${cell.section !== undefined && cell.section !== null ? ` (S${cell.section})` : ''}`;
                      }
                      return (
                        <View key={period} style={[styles.tableCol, { width: getColWidth(false) }]}>
                          <Text style={styles.tableCell}>{content}</Text>
                        </View>
                      );
                    })}
                  </View>
                ))}
              </View>
            </View>
          ))}
          <Text 
            style={{ position: 'absolute', fontSize: 10, bottom: 20, left: 0, right: 0, textAlign: 'center', color: 'grey' }} 
            render={({ pageNumber, totalPages }) => `${pageNumber} / ${totalPages}`} 
            fixed 
          />
        </Page>
      )}
    </Document>
  );
};

export default TimetablePDF;
