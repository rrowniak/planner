# planner
A simple tool for project planning and drawing Gantt charts.

One of the most challenging aspects of project management is accurately translating project estimates into a real-world timeline. This task is far from straightforward, as it requires accounting for numerous variables, such as weekends, holidays, public holidays, team members' other commitments, focus levels, task dependencies, and more. A common, but overly simplistic, approach is to treat estimates in isolation. For example, if a project is estimated to take 17 man-days, one might assume it will be completed in roughly three and a half weeks (based on a five-day workweek). Starting on October 1st, you'd expect the project to wrap up by October 24th. However, this assumption rarely holds up in practice. Below, we illustrate the more realistic calculations. 

![Simple example](./examples/simple_project.png)

As you can see, the project actually finishes at the end of November, far beyond our initial estimate. Mistakes like this are surprisingly common and often lead to confusion, misalignment, and unnecessary tension within teams.

The planner takes a ![project definition](./examples/simple_project.toml) as input, with a self-explanatory format. In this definition, we specify the team members involved, the tasks with their respective dependencies, and the task assignments. Based on this information, the planner performs all the necessary calculations and generates a Gantt chart, accurately reflecting the timeline.

Here you can see a bit more complex scenario defined ![here](./examples/complex_project.toml):

![Complex example](./examples/complex_project.png)

## Dependencies
Project is written in Rust, you need to have a Rust development environment.
### Plantuml
The planner relies on the plantuml library, an opensource tool for drawing different kind of diagram, including Gantt charts.
Install plantuml first:
- install JRE, e.g. on Ubuntu:
```
sudo apt install default-jre
```
- download th plantuml jar library

## Build and install
Build the project
```
cargo build
```
