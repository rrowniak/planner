use chrono::{Datelike, NaiveDate, Weekday};
use serde::Deserialize;

const DATE_FMT: &str = "%Y-%m-%d";

#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub enum DateObj {
    Date(NaiveDate),
    Range(NaiveDate, NaiveDate),
}

#[derive(Debug, Deserialize)]
pub struct PublicHoliday {
    #[serde(deserialize_with = "parse_multidate_entry")]
    pub date: Vec<DateObj>,
    pub name: String,
}

#[derive(Debug, Deserialize)]
pub struct BusinessDaysCalendar {
    pub closed_days: Vec<Weekday>,
    pub working_hrs_in_day: u32,
    pub public_holidays: Vec<PublicHoliday>,
}

pub fn parse_multidate_entry<'de, D>(deserializer: D) -> Result<Vec<DateObj>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let s: String = String::deserialize(deserializer)?;
    let mut ret = Vec::new();
    for d in s.split(',').filter(|s| !s.trim().is_empty()) {
        if let Some(range) = s.split_once(':') {
            let start_date =
                NaiveDate::parse_from_str(range.0, DATE_FMT).map_err(serde::de::Error::custom)?;
            let end_date =
                NaiveDate::parse_from_str(range.1, DATE_FMT).map_err(serde::de::Error::custom)?;
            ret.push(DateObj::Range(start_date, end_date));
        } else {
            ret.push(DateObj::Date(
                NaiveDate::parse_from_str(&d, DATE_FMT).map_err(serde::de::Error::custom)?,
            ));
        }
    }
    Ok(ret)
}

pub fn parse_date_entry<'de, D>(deserializer: D) -> Result<NaiveDate, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let s: String = String::deserialize(deserializer)?;
    Ok(NaiveDate::parse_from_str(&s, DATE_FMT).map_err(serde::de::Error::custom)?)
}

pub enum DayInfo {
    NonWorking,
    NonWorkingPubHoliday,
    WorkingDay(u32),
}

impl BusinessDaysCalendar {
    pub fn from(contents: &str) -> Result<BusinessDaysCalendar, Box<dyn std::error::Error>> {
        let cal: Self = toml::from_str(&contents)?;
        Ok(cal)
    }

    pub fn year_covered(&self, year: u32) -> bool {
        let year = year as i32;
        for h in self.public_holidays.iter().flat_map(|h| &h.date) {
            match h {
                DateObj::Date(d) => {
                    if d.year() == year {
                        return true;
                    }
                }
                DateObj::Range(f, t) => {
                    if f.year() <= year || t.year() >= year {
                        return true;
                    }
                }
            }
        }
        false
    }

    pub fn day_info(&self, d: &NaiveDate) -> DayInfo {
        if self.closed_days.contains(&d.weekday()) {
            return DayInfo::NonWorking;
        }
        // dummy & inneficient but simple: iterate over all holidays
        for h in self.public_holidays.iter().flat_map(|h| &h.date) {
            match h {
                DateObj::Date(dd) => {
                    if dd == d {
                        return DayInfo::NonWorkingPubHoliday;
                    }
                }
                DateObj::Range(f, t) => {
                    if f <= d || t >= d {
                        return DayInfo::NonWorkingPubHoliday;
                    }
                }
            }
        }

        DayInfo::WorkingDay(self.working_hrs_in_day)
    }
}

pub fn in_date_obj_vec(d: &NaiveDate, dates: &[DateObj]) -> bool {
    for dt in dates.iter() {
        match dt {
            DateObj::Date(dd) if dd == d => return true,
            DateObj::Range(f, t) if f <= d && d <= t => return true,
            _ => {}
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::NaiveDate;
    #[test]
    fn test_example_cal() {
        let cal = BusinessDaysCalendar::from(include_str!("../../examples/calendar_pl.toml"));
        if let Err(e) = &cal {
            eprintln!("Parsing error: {e}");
        }
        assert!(cal.is_ok());
        let cal = cal.unwrap();
        assert_eq!(cal.public_holidays.len(), 26);
        assert_eq!(
            cal.public_holidays[0].date[0],
            DateObj::Date(NaiveDate::parse_from_str("2024-01-01", DATE_FMT).unwrap())
        );
    }
}
