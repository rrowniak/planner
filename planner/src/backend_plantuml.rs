use crate::cfg;
use crate::gantt_builder;
use std::process::{Command, Output};

#[derive(Debug, Clone)]
struct GenError(String);

impl std::fmt::Display for GenError {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        write!(f, "Plantuml generator error: {}", self.0)
    }
}

impl std::error::Error for GenError {}

pub fn build_chart(
    cfg: &cfg::Config,
    data: &gantt_builder::GanttData,
    api_server: bool,
    out_dir: &std::path::Path,
    proj_name: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let script = generate_plantuml_script(data)?;
    if api_server {
    } else {
        let mut script_filename = std::path::PathBuf::from(out_dir);
        script_filename.push(&format!("{proj_name}.txt"));
        generate_plantuml_diagram(cfg, out_dir, &script, &script_filename)?;
    }
    Ok(())
}

fn generate_plantuml_script(
    data: &gantt_builder::GanttData,
) -> Result<String, Box<dyn std::error::Error>> {
    let mut script = String::new();
    script += "@startgantt\n";
    // Closed days
    for cd in &data.closed_days {
        let cd = format!("{cd} are closed\n").to_lowercase();
        script += &cd;
    }
    // Workers absence days
    for (work, off) in &data.workers_absence {
        for d in off {
            script += &format!("{{{work}}} is off on {d}\n");
        }
    }
    // Public holidays (for all callendars)
    for ph in &data.public_holidays {
        script += &format!("{ph} is colored in salmon\n");
    }
    // Project start date
    script += &format!("\nProject starts {}\n\n", data.project_starts);
    // Task starting and finishing dates
    for t in &data.tasks {
        let name = &t.name;
        let id = &t.id;
        let assignee = &t.assignee;
        script += &format!(
            "[{name}] as [{id}] on {{{assignee}}} starts {}\n",
            t.start_on
        );
        let end = t.end_on;
        script += &format!("[{id}] ends at {end}\n");
        // paused days
        for p in t.pause_days.iter() {
            script += &format!("[{id}] pauses on {p}\n");
        }
    }
    script += "\n";
    // Dependencies
    for t in &data.tasks {
        let id = &t.id;
        for after in &t.after {
            script += &format!("[{after}] -> [{id}]\n")
        }
    }

    script += "@endgantt\n";
    Ok(script)
}

fn generate_plantuml_diagram(
    cfg: &cfg::Config,
    out_dir: &std::path::Path,
    script: &str,
    script_file: &std::path::Path,
) -> Result<(), Box<dyn std::error::Error>> {
    // save script to file
    std::fs::write(script_file, script)?;
    let input = script_file.to_string_lossy();
    let output = out_dir.to_string_lossy();
    let mut cmd_args = cfg.backend.plantuml.local_cmd.split(' ').map(|a| {
        if a == "<INPUT>" {
            &input
        } else if a == "<OUTPUT_DIR>" {
            &output
        } else {
            a
        }
    });
    let command_result: Output =
        Command::new(cmd_args.next().expect("invalid local_cmd config option"))
            .args(cmd_args)
            .output()
            .expect("Failed to execute command");

    // Get the exit status code
    let exit_code = command_result.status.code().unwrap_or(-1);

    // Convert the output (stdout) to a String
    let stdout = String::from_utf8_lossy(&command_result.stdout).to_string();

    // Convert the error output (stderr) to a String if needed
    let stderr = String::from_utf8_lossy(&command_result.stderr).to_string();

    // Check the return code
    if exit_code == 0 {
        println!("{stdout}");
        Ok(())
    } else {
        Err(report_err(stderr))
    }
}

fn report_err(msg: String) -> Box<GenError> {
    Box::new(GenError(msg))
}
