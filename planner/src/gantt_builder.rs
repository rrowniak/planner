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
pub struct ResourceAllocation(pub HashMap<String, BTreeMap<NaiveDate, WorkerDay>>);

impl ResourceAllocation {
    fn new() -> ResourceAllocation {
        ResourceAllocation(HashMap::new())
    }

    fn add(&mut self, worker: &str, date: NaiveDate, day: WorkerDay) {
        let worker = worker.into();
        let m = self.0.entry(worker).or_default();
        if let Some(v) = m.get_mut(&date) {
            if *v == WorkerDay::Fine {
                *v = WorkerDay::Overloaded;
            }
        } else {
            m.insert(date, day);
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
        let mut hours_to_burn = task.estimate * 8.0;
        let mut end_on = start_on;
        for d in start_on.iter_days() {
            cumulative_days += 1.0;
            let day_info = get_day_info(&d, worker_cal, worker);
            let hrs = match day_info {
                calendar::DayInfo::WorkerHolidays | calendar::DayInfo::WorkerOtherDuties => {
                    workers_absence
                        .entry(worker_name.clone())
                        .or_default()
                        .push(d);
                    if day_info == calendar::DayInfo::WorkerHolidays {
                        resource_allocation.add(&worker_name, d, WorkerDay::Holidays);
                    } else {
                        resource_allocation.add(&worker_name, d, WorkerDay::OtherDuties);
                    }
                    pause_days.push(d);
                    continue;
                }
                calendar::DayInfo::WorkingDay(h) => h,
                calendar::DayInfo::NonWorkingPubHoliday => {
                    public_holidays.push(d);
                    workers_absence
                        .entry(worker_name.clone())
                        .or_default()
                        .push(d);
                    resource_allocation.add(&worker_name, d, WorkerDay::PubHolidays);
                    pause_days.push(d);
                    continue;
                }
                _ => {
                    pause_days.push(d);
                    resource_allocation.add(&worker_name, d, WorkerDay::PubHolidays);
                    continue;
                }
            };
            // calculate effective amount of hours
            // focus_factor
            let focus_factor = match assignment.focus_factor {
                Some(f) => f,
                None => worker.focus_factor,
            };
            let hrs = hrs as f64 * focus_factor;
            hours_to_burn -= hrs;
            resource_allocation.add(&worker_name, d, WorkerDay::Fine);
            if hours_to_burn <= 0.01 {
                // we have to subtract (hours_to_burn is negative) remaining day
                // as we progressed too far
                cumulative_days += hours_to_burn / hrs;
                // println!("CD={cumulative_days}");
                end_on = project_begin + Days::new(cumulative_days.ceil() as u64 - 1);
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
            days.entry(d).or_insert(WorkerDay::Unassigned);
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
