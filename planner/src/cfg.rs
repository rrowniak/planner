use serde::Deserialize;
// Define a struct for plantuml settings
#[derive(Debug, Deserialize)]
pub struct PlantUMLConfig {
    pub use_api: bool,
    pub api_url: String,
    pub local_cmd: String,
}

// Define a struct for backend settings, which contains plantuml configuration
#[derive(Debug, Deserialize)]
pub struct BackendConfig {
    pub plantuml: PlantUMLConfig,
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
