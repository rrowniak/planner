use serde::Deserialize;
// Define a struct for plantuml settings
#[derive(Debug, Deserialize)]
pub struct PlantUMLConfig {
    pub use_api: bool,
    pub api_url: String,
    pub local_cmd: String,
}

#[derive(Debug, Deserialize)]
pub struct Colors {
    pub worker_pub_holidays: String,
    pub worker_holidays: String,
    pub worker_other_duties: String,
    pub worker_overloaded: String,
    pub worker_underloaded: String,
    pub worker_fine: String,
    pub worker_unassigned: String,
}

// Define a struct for backend settings, which contains plantuml configuration
#[derive(Debug, Deserialize)]
pub struct BackendConfig {
    pub plantuml: PlantUMLConfig,
    pub colors: Colors,
}

// Define the top-level configuration struct
#[derive(Debug, Deserialize)]
pub struct Config {
    pub backend: BackendConfig,
}

impl Config {
    pub fn from(contents: &str) -> Result<Config, Box<dyn std::error::Error>> {
        // Parse the TOML contents into the Config struct
        let config: Config = toml::from_str(&contents)?;

        Ok(config)
    }
}

#[cfg(test)]
mod test {
    use super::*;
    #[test]
    fn test_default_cfg() {
        let cfg = Config::from(include_str!("../../default.cfg.toml"));
        assert!(cfg.is_ok());
        let cfg = cfg.unwrap();
        assert_eq!(cfg.backend.plantuml.use_api, true);
    }
}
