use crate::{calendar, cfg, project};
use chrono::{Days, NaiveDate, Weekday};
use std::cell::Cell;
use std::collections::{BTreeMap, HashMap, VecDeque};

#[derive(Debug, Clone)]
struct ProcessError(String);

impl std::fmt::Display for ProcessError {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        write!(f, "Processor error: {}", self.0)
    }
}

impl std::error::Error for ProcessError {}

#[derive(Debug)]
pub struct Task {
    pub id: String,
    pub name: String,
    pub assignee: String,
    pub after: Vec<String>,
    pub start_on: NaiveDate,
    pub end_on: NaiveDate,
    pub pause_days: Vec<NaiveDate>,
    pub duration_hours: u32,
}

#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub enum WorkerDay {
    PubHolidays,
    Holidays,
    OtherDuties,
    Overloaded,
    Underloaded,
    Fine,
    Unassigned,
}

#[derive(Debug)]
pub struct Hours(pub f64);

#[derive(Debug)]
pub struct ResourceAllocation(pub BTreeMap<String, BTreeMap<NaiveDate, (Hours, WorkerDay)>>);

impl ResourceAllocation {
    fn new() -> ResourceAllocation {
        ResourceAllocation(BTreeMap::new())
    }

    fn add(&mut self, worker: &str, date: NaiveDate, day: WorkerDay, hours: Hours) {
        let worker = worker.into();
        let m = self.0.entry(worker).or_default();
        if let Some(v) = m.get_mut(&date) {
            *v = (Hours(v.0 .0 + hours.0), day)
        } else {
            m.insert(date, (hours, day));
        }
    }
}

#[derive(Debug)]
pub struct GanttData {
    pub title: String,
    pub tasks: Vec<Task>,
    pub project_starts: NaiveDate,
    pub closed_days: Vec<Weekday>,
    /// <worker_name, [absences]>
    pub workers_absence: HashMap<String, Vec<NaiveDate>>,
    pub public_holidays: Vec<NaiveDate>,
    pub resource_allocation: ResourceAllocation,
    pub time_markers: Vec<project::TimeMarker>,
}

#[derive(Debug, Copy, Clone)]
struct ProjTaskIndx(usize);

impl ProjTaskIndx {
    fn get<'a>(&self, tasks: &'a [project::Task]) -> Option<&'a project::Task> {
        if self.0 >= tasks.len() {
            None
        } else {
            Some(&tasks[self.0])
        }
    }
}

#[derive(Debug, Copy, Clone)]
struct GraphNodeId(usize);

#[derive(Debug)]
struct Graph {
    starting_points: Vec<GraphNodeId>,
    graph: Vec<GraphNode>,
}

impl Graph {
    fn get_node(&self, id: GraphNodeId) -> Option<&GraphNode> {
        if id.0 >= self.graph.len() {
            None
        } else {
            Some(&self.graph[id.0])
        }
    }

    fn calc_start_time(&self, n: &GraphNode) -> bool {
        let mut cumulative_days = 0_f64;
        for p in &n.parents {
            let par = self.get_node(*p).unwrap();
            if let Some(s) = par.cumulative_days.get() {
                cumulative_days = cumulative_days.max(s);
            } else {
                return false;
            }
        }
        n.cumulative_days.set(Some(cumulative_days));
        true
    }
}

#[derive(Debug)]
struct GraphNode {
    task_id: ProjTaskIndx,
    cumulative_days: Cell<Option<f64>>,
    parents: Vec<GraphNodeId>,
    children: Vec<GraphNodeId>,
}

fn build_task_graph(tasks: &[project::Task]) -> Graph {
    let mut lookup = HashMap::new();
    let mut starting_points = Vec::new();
    let mut graph = Vec::with_capacity(tasks.len());
    // build graph array and lookup table
    for (i, task) in tasks.iter().enumerate() {
        let task_id = ProjTaskIndx(i);
        let parents = Vec::new();
        let children = Vec::new();
        let cumulative_days = Cell::new(None);
        if task.after.is_empty() {
            starting_points.push(GraphNodeId(graph.len()));
        }
        lookup.insert(&task.id, GraphNodeId(i));
        graph.push(GraphNode {
            task_id,
            cumulative_days,
            parents,
            children,
        });
    }
    // update dependencies
    for i in 0..graph.len() {
        let task = &tasks[graph[i].task_id.0];
        for after in &task.after {
            // update: parent's children
            let parent_id = *lookup.get(&after).unwrap();
            let parent_node = &mut graph[parent_id.0];
            parent_node.children.push(GraphNodeId(i));
            // update node parent
            graph[i].parents.push(parent_id)
        }
    }
    Graph {
        starting_points,
        graph,
    }
}

fn get_day_info(
    d: &NaiveDate,
    cal: &calendar::BusinessDaysCalendar,
    worker: &project::TeamMember,
) -> calendar::DayInfo {
    let hrs = match cal.day_info(d) {
        calendar::DayInfo::WorkingDay(h) => h,
        di => return di,
    };
    if calendar::in_date_obj_vec(d, &worker.holidays) {
        return calendar::DayInfo::WorkerHolidays;
    }
    if calendar::in_date_obj_vec(d, &worker.other_duties) {
        return calendar::DayInfo::WorkerOtherDuties;
    }
    // todo: worker might have a custom settings about the
    // length of a working day
    calendar::DayInfo::WorkingDay(hrs)
}

fn get_working_day_len(
    day_info: &calendar::DayInfo,
    d: NaiveDate,
    worker_name: &String,
    workers_absence: &mut HashMap<String, Vec<NaiveDate>>,
    resource_allocation: &mut ResourceAllocation,
    pause_days: &mut Vec<NaiveDate>,
    public_holidays: &mut Vec<NaiveDate>,
) -> Option<u32> {
    match day_info {
        calendar::DayInfo::WorkerHolidays | calendar::DayInfo::WorkerOtherDuties => {
            workers_absence
                .entry(worker_name.clone())
                .or_default()
                .push(d);
            if *day_info == calendar::DayInfo::WorkerHolidays {
                resource_allocation.add(&worker_name, d, WorkerDay::Holidays, Hours(0.0));
            } else {
                resource_allocation.add(&worker_name, d, WorkerDay::OtherDuties, Hours(0.0));
            }
            pause_days.push(d);
            None
        }
        calendar::DayInfo::WorkingDay(h) => Some(*h),
        calendar::DayInfo::NonWorkingPubHoliday => {
            public_holidays.push(d);
            workers_absence
                .entry(worker_name.clone())
                .or_default()
                .push(d);
            resource_allocation.add(&worker_name, d, WorkerDay::PubHolidays, Hours(0.0));
            pause_days.push(d);
            None
        }
        _ => {
            pause_days.push(d);
            resource_allocation.add(&worker_name, d, WorkerDay::PubHolidays, Hours(0.0));
            None
        }
    }
}

pub fn process(
    _cfg: &cfg::Config,
    proj: &project::ProjectConfig,
    calendars: &HashMap<&String, calendar::BusinessDaysCalendar>,
) -> Result<GanttData, Box<dyn std::error::Error>> {
    let graph = build_task_graph(&proj.tasks);
    let mut task_queue = VecDeque::new();
    task_queue.extend(&graph.starting_points);
    let mut tasks = Vec::new();
    let mut workers_absence = HashMap::<String, Vec<NaiveDate>>::new();
    let mut public_holidays = Vec::new();
    let mut resource_allocation = ResourceAllocation::new();
    let project_begin = proj.start_date;
    let mut project_end = project_begin;
    // println!("Graph: {graph:?}");
    while let Some(graph_node_id) = task_queue.pop_front() {
        let graph_node = graph.get_node(graph_node_id).unwrap();
        let task = graph_node.task_id.get(&proj.tasks).unwrap();
        let id = task.id.clone();
        let name = task.name.clone();
        // println!("Processing: {name}, after: {:?}", task.after);
        if graph_node.cumulative_days.get().is_some() {
            continue;
        }
        // ready for processing?
        if !graph.calc_start_time(graph_node) {
            // this node (task) can't be processed as one of its parent
            // is not computed yet.
            task_queue.push_back(graph_node_id);
            continue;
        } else {
            // task_queue.extend(&graph_node.children);
            // kind of a trick - place at the front just to go
            // as far as possible with this path
            for ch in &graph_node.children {
                task_queue.push_front(*ch);
            }
        }
        // let process this node (task)
        let mut cumulative_days = graph_node.cumulative_days.get().unwrap();
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
        let after = task.after.clone();
        let start_on = project_begin + Days::new(cumulative_days as u64);
        let mut pause_days = Vec::new();
        // calculate task length based on real calendar and focus factor
        // TODO: replace the hardcoded day length with proper value defined in the cal
        let mut hours_to_burn = task.estimate * 8.0;
        let mut end_on = start_on;
        // println!("Task: {name}");
        for d in start_on.iter_days() {
            let day_info = get_day_info(&d, worker_cal, worker);
            let working_hrs = if let Some(h) = get_working_day_len(
                &day_info,
                d,
                &worker_name,
                &mut workers_absence,
                &mut resource_allocation,
                &mut pause_days,
                &mut public_holidays,
            ) {
                h
            } else {
                cumulative_days += 1.0;
                continue;
            };
            // calculate effective amount of hours
            let focus_factor = match assignment.focus_factor {
                Some(f) => f,
                None => worker.focus_factor,
            };
            let mut effective_working_hrs = working_hrs as f64 * focus_factor;
            // what if a previous task finished in this day?
            // we need to adjust currently available hours
            let left_day = cumulative_days % 1.0;
            let mut cumulative_day_len = 1.0;
            if left_day.abs() > 0.001 {
                // prev task was finished in this day
                let remaining_fraction = 1.0 - left_day;
                effective_working_hrs *= remaining_fraction;
                cumulative_day_len *= remaining_fraction;
            }
            let mut task_ends = false;

            // println!("{name} => {hours_to_burn} (cum: {cumulative_days})");
            if hours_to_burn >= effective_working_hrs {
                // whole day will be assigned to this task
                hours_to_burn -= effective_working_hrs;
                cumulative_days += cumulative_day_len;
                resource_allocation.add(
                    &worker_name,
                    d,
                    WorkerDay::Fine,
                    Hours(8.0 * cumulative_day_len),
                );
                if hours_to_burn.abs() < 1e-10 {
                    task_ends = true;
                }
            } else {
                // only a fraction of this day will be assigned to the task
                // (effectively this task is about to be finished)
                assert!(effective_working_hrs != 0.0);
                let fraction = hours_to_burn / effective_working_hrs;
                assert!(fraction <= 1.0);
                cumulative_days += cumulative_day_len * fraction;
                resource_allocation.add(
                    &worker_name,
                    d,
                    WorkerDay::Underloaded,
                    Hours(8.0 * fraction * cumulative_day_len),
                );
                task_ends = true;
            }
            if task_ends {
                end_on = project_begin + Days::new(cumulative_days.ceil() as u64 - 1);
                // println!("end on: {end_on}");
                break;
            }
        }
        if end_on > project_end {
            project_end = end_on;
        }
        let duration_hours = (24.0 * task.estimate) as u32;
        tasks.push(Task {
            id,
            name,
            assignee: worker_name,
            after,
            start_on,
            end_on,
            duration_hours,
            pause_days,
        });
        // we have to update new cumulative_days
        graph_node.cumulative_days.set(Some(cumulative_days));
    }
    // fill resource allocation unassigned
    for (_, days) in resource_allocation.0.iter_mut() {
        for d in project_begin.iter_days() {
            if d > project_end {
                break;
            }
            let d = &mut days.entry(d).or_insert((Hours(0.0), WorkerDay::Unassigned));

            let h = d.0 .0;

            if h >= 8.001 {
                d.1 = WorkerDay::Overloaded;
                println!("Overloaded: {h}");
            } else if h <= 7.999 && h >= 0.001 {
                d.1 = WorkerDay::Underloaded;
            } else if h > 7.999 && h < 8.001 {
                d.1 = WorkerDay::Fine;
            }
        }
    }

    let project_starts = proj.start_date;
    let closed_days = calendars.values().next().unwrap().closed_days.clone();
    let time_markers = proj.time_markers.clone().unwrap_or_default();
    Ok(GanttData {
        title: proj.project_name.clone(),
        tasks,
        project_starts,
        closed_days,
        workers_absence,
        public_holidays,
        resource_allocation,
        time_markers,
    })
}

fn report_err(msg: String) -> Box<ProcessError> {
    Box::new(ProcessError(msg))
}
