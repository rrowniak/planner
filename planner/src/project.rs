use crate::calendar::{parse_date_entry, parse_multidate_entry, DateObj};
use chrono::NaiveDate;
use toml;
use serde::{self, Deserialize};

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
    #[serde(default, deserialize_with="parse_vec_str")]
    pub after: Vec<String>, // This is an optional field
}

pub fn parse_vec_str<'de, D>(deserializer: D) -> Result<Vec<String>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let s: String = String::deserialize(deserializer)?;
    let mut ret = Vec::new();
    for s in s.split(',').filter(|s| !s.trim().is_empty()) {
        ret.push(s.trim().into());
    }
    Ok(ret)
}

#[derive(Debug, Deserialize)]
pub struct Assignment {
    pub task: String,
    pub owner: String,
    pub focus_factor: Option<f64>, // Optional field for overriding focus factor
}

#[derive(Debug, Clone, Deserialize)]
pub struct TimeMarker {
    #[serde(deserialize_with="parse_multidate_entry")]
    pub time: Vec<DateObj>,
    pub label: String,
    pub color: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct ProjectConfig {
    pub project_name: String,
    #[serde(deserialize_with = "parse_date_entry")]
    pub start_date: NaiveDate, // Parsing date in "YYYY-MM-DD" format
    pub team: Vec<TeamMember>,
    pub tasks: Vec<Task>,
    pub assignments: Vec<Assignment>,
    pub time_markers: Option<Vec<TimeMarker>>,
}

impl ProjectConfig {
    pub fn from(content: &str) -> Result<ProjectConfig, Box<dyn std::error::Error>> {
        let config: ProjectConfig = toml::from_str(content)?;
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

  #[test]
    fn complex_project_test() {
        let proj = ProjectConfig::from(include_str!("../../examples/complex_project.toml"));
        if let Err(e) = &proj {
            println!("Error: {e}");
        }
        assert!(proj.is_ok());
        let proj = proj.unwrap();
        assert_eq!(proj.project_name, "Game development");
    }

}
