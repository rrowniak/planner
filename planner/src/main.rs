use clap::Parser;
use planner::{backend_plantuml, calendar, cfg, gantt_builder, project};
use std::collections::HashMap;
use std::path::PathBuf;
use std::{env, fs};

#[derive(Debug, Parser)]
#[command(name = "planner")]
#[command(version = "1.0")]
#[command(about = "Draws a Gantt chart based on the input project", long_about = None)]
struct Args {
    #[arg(short, long)]
    api_server: bool,
    #[arg(value_name = "PROJECT_TOML")]
    project_file: PathBuf,
    #[arg(short = 'c', long = "cfg", value_name = "CONFIG")]
    config_file: Option<PathBuf>,
}

fn do_the_calc(args: &Args) -> Result<(), Box<dyn std::error::Error>> {
    let cfg = if let Some(config_file) = &args.config_file {
        cfg::Config::from(&fs::read_to_string(config_file)?)?
    } else {
        cfg::Config::from(include_str!("../../default.cfg.toml"))?
    };
    let proj = project::ProjectConfig::from(&fs::read_to_string(&args.project_file)?)?;
    let mut calendars = HashMap::new();
    let mut full_path = env::current_dir()?;
    if args.project_file.parent().is_some() {
        full_path.push(args.project_file.parent().unwrap());
    }
    for cal_file in proj.team.iter().map(|user| &user.base_calendar) {
        let mut full_path = full_path.clone();
        full_path.push(cal_file);
        calendars
            .entry(cal_file)
            .or_insert(calendar::BusinessDaysCalendar::from(&fs::read_to_string(
                full_path,
            )?)?);
    }
    backend_plantuml::build_chart(
        &cfg,
        &gantt_builder::process(&cfg, &proj, &calendars)?,
        args.api_server,
        &full_path,
        &args.project_file.file_stem().unwrap().to_string_lossy()
    )?;
    Ok(())
}

fn main() {
    let args = Args::parse();
    if let Err(e) = do_the_calc(&args) {
        eprintln!("Error: {e}");
    }
}
