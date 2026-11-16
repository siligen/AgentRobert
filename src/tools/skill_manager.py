import os

class SkillManager:
    """
    Manages the discovery and parsing of 'skills' defined in the filesystem.
    Skills are stored as directories within the 'skills/' folder, each containing a 'SKILL.md'.
    """
    def __init__(self, workspace_dir, app_start_dir):
        self.workspace_dir = workspace_dir
        self.app_start_dir = app_start_dir
        self.skills = {}
        self.refresh_skills()

    def refresh_skills(self):
        """Scans the skills directory in both workspace and app start dir."""
        self.skills = {}
        
        # Paths to check for a 'skills/' directory
        search_paths = [
            os.path.join(self.app_start_dir, "skills"),
            os.path.join(self.workspace_dir, "skills")
        ]

        for base_path in search_paths:
            if os.path.isdir(base_path):
                try:
                    for entry in os.scandir(base_path):
                        if entry.is_dir():
                            skill_path = os.path.join(entry.path, "SKILL.md")
                            if os.path.exists(skill_path):
                                skill_name = entry.name
                                with open(skill_path, "r", encoding="utf-8") as f:
                                    content = f.read()
                                    self.skills[skill_name] = {
                                        "name": skill_name,
                                        "details": content,
                                        "path": skill_path
                                    }
                except Exception as e:
                    print(f"Error scanning skills in {base_path}: {e}")

    def list_skills(self):
        """Returns a list of all discovered skill names."""
        return list(self.skills.keys())

    def get_skill(self, skill_name):
        """Returns the details of a specific skill."""
        return self.skills.get(skill_name)

    def get_all_skills_summary(self):
        """Returns a summary string of all available skills for the system prompt."""
        if not self.skills:
            return "No specialized skills currently installed."
        
        summary = "AVAILABLE SYSTEM SKILLS:\n"
        for name in self.skills:
            summary += f"- {name} (Path: skills/{name}/SKILL.md)\n"
        return summary
