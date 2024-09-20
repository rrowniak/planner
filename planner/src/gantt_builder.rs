use crate::{calendar, cfg, project};
use chrono::{Days, NaiveDate, Weekday};
use std::collections::HashMap;

#[derive(Debug, Clone)]
struct ProcessError(String);

impl std::fmt::Display for ProcessError {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        write!(f, "Processor error: {}", self.0)
    }
}

impl std::error::Error for ProcessError {}

struct ProjTaskIndx(usize);

#[derive(Debug)]
pub struct Task {
    pub id: String,
    pub name: String,
    pub assignee: String,
    pub after: Option<String>,
    pub start_on: NaiveDate,
    pub end_on: NaiveDate,
    pub duration_hours: u32,
}

#[derive(Debug)]
pub struct GanttData {
    pub tasks: Vec<Task>,
    pub project_starts: NaiveDate,
    pub closed_days: Vec<Weekday>,
}

fn find_starting_tasks(tasks: &[project::Task]) -> Vec<ProjTaskIndx> {
    todo!()
}

fn get_available_hours(
    d: &NaiveDate,
    cal: &calendar::BusinessDaysCalendar,
    worker: &project::TeamMember,
) -> u32 {
    let hrs = if let calendar::DayInfo::WorkingDay(hrs) = cal.day_info(d) {
        hrs
    } else {
        return 0;
    };
    if calendar::in_date_obj_vec(d, &worker.holidays) {
        return 0;
    }
    if calendar::in_date_obj_vec(d, &worker.other_duties) {
        return 0;
    }
    // todo: worker might have a custom settings about the
    // length of a working day
    hrs
}

pub fn process(
    _cfg: &cfg::Config,
    proj: &project::ProjectConfig,
    calendars: &HashMap<&String, calendar::BusinessDaysCalendar>,
) -> Result<GanttData, Box<dyn std::error::Error>> {
    let mut tasks = Vec::new();
    let mut now = proj.start_date;
    // let mut cumulative_days = 0 as f64;
    for t in &proj.tasks {
        let id = t.id.clone();
        let name = t.name.clone();
        let assignment = if let Some(e) = proj.assignments.iter().find(|a| a.task == id) {
            e
        } else {
            return Err(report_err(format!("Task '{name}' is not assigned")));
        };
        let worker_name = assignment.owner.clone();
        let worker = if let Some(w) = proj.team.iter().find(|u| u.name == assignment.owner) {
            w
        } else {
            return Err(report_err(format!("Worker '{worker_name}' not defined")));
        };
        let worker_cal = calendars.get(&worker.base_calendar).unwrap();
        let after = t.after.clone();
        let start_on = now; // + Days::new(cumulative_days as u64);
                            // calculate task length based on real calendar and focus factor
        let mut hours_to_burn = t.estimate * 8.0;
        let mut end_on = start_on;
        for d in start_on.iter_days() {
            let hrs = get_available_hours(&d, worker_cal, worker);
            if hrs == 0 {
                continue;
            }
            // calculate effective amount of hours
            // focus_factor
            let focus_factor = match assignment.focus_factor {
                Some(f) => f,
                None => worker.focus_factor,
            };
            let hrs = hrs as f64 * focus_factor;
            hours_to_burn -= hrs;
            if hours_to_burn <= 0.0 {
                end_on = d;
                break;
            }
        }
        // let end_on = start_on + Days::new(t.estimate as u64);
        // cumulative_days += t.estimate;
        now = end_on;
        let duration_hours = (24.0 * t.estimate) as u32;
        tasks.push(Task {
            id,
            name,
            assignee: worker_name,
            after,
            start_on,
            end_on,
            duration_hours,
        });
    }
    let project_starts = proj.start_date;
    let closed_days = calendars.values().next().unwrap().closed_days.clone();
    Ok(GanttData {
        tasks,
        project_starts,
        closed_days,
    })
}

fn report_err(msg: String) -> Box<ProcessError> {
    Box::new(ProcessError(msg))
}
