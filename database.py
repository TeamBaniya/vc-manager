import json
import os

DB_FILE = "groups_config.json"

class Database:
    def __init__(self):
        self.data = {}
        self.load()
    
    def load(self):
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r') as f:
                self.data = json.load(f)
        else:
            self.data = {}
    
    def save(self):
        with open(DB_FILE, 'w') as f:
            json.dump(self.data, f, indent=4)
    
    def add_group(self, group_id, group_type, group_identifier):
        """Add or update group configuration"""
        self.data[str(group_id)] = {
            "type": group_type,  # "public" or "private"
            "identifier": group_identifier,  # username or invite link
            "active": True
        }
        self.save()
    
    def get_group(self, group_id):
        """Get group configuration"""
        return self.data.get(str(group_id))
    
    def remove_group(self, group_id):
        """Remove group configuration"""
        if str(group_id) in self.data:
            del self.data[str(group_id)]
            self.save()
    
    def get_all_groups(self):
        """Get all groups"""
        return self.data
