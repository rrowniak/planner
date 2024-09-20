use crate::calendar::{parse_date_entry, parse_multidate_entry, DateObj};
use chrono::NaiveDate;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub struct TeamMember {
    pub name: String,
    pub base_calendar: String,
    pub focus_factor: f64,
    #[serde(deserialize_with="parse_multidate_entry")]
    pub holidays: Vec<DateObj>,
    #[serde(deserialize_with="parse_multidate_entry")]
    pub other_duties: Vec<DateObj>,
}

#[derive(Debug, Deserialize)]
pub struct Task {
    pub id: String,
    pub name: String,
    pub estimate: f64,
    pub after: Option<String>, // This is an optional field
}

#[derive(Debug, Deserialize)]
pub struct Assignment {
    pub task: String,
    pub owner: String,
    pub focus_factor: Option<f64>, // Optional field for overriding focus factor
}

#[derive(Debug, Deserialize)]
pub struct ProjectConfig {
    pub project_name: String,
    #[serde(deserialize_with = "parse_date_entry")]
    pub start_date: NaiveDate, // Parsing date in "YYYY-MM-DD" format
    pub team: Vec<TeamMember>,
    pub tasks: Vec<Task>,
    pub assignments: Vec<Assignment>,
}

impl ProjectConfig {
    pub fn from(content: &str) -> Result<ProjectConfig, Box<dyn std::error::Error>> {
        let config: ProjectConfig = toml::from_str(&content)?;
        Ok(config)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn simple_project_test() {
        let proj = ProjectConfig::from(include_str!("../../examples/simple_project.toml"));
        if let Err(e) = &proj {
            println!("Error: {e}");
        }
        assert!(proj.is_ok());
        let proj = proj.unwrap();
        assert_eq!(proj.project_name, "Web notes assistant");
    }
}
