"""Studio-owned groups, keyed by permanent module IDs."""

from copy import deepcopy
import json
import os
from pathlib import Path
import secrets
from threading import RLock

from network import DEVICE_ID
from patches import ROOT


class GroupConflict(ValueError):
    pass


class ModuleGroups:
    def __init__(self, path=None):
        self.path = Path(path) if path else ROOT / 'build/host/private/module-groups.json'
        self.lock = RLock()
        self._groups = None

    def _read(self):
        if self._groups is None:
            self._groups = json.loads(self.path.read_text()) if self.path.exists() else {}
            if not isinstance(self._groups, dict):
                self._groups = None
                raise ValueError('Invalid module group store')
        return self._groups

    def snapshot(self):
        with self.lock:
            return deepcopy(self._read())

    def _write(self, groups):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name('.groups-' + secrets.token_hex(8))
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump(groups, stream, indent=2, ensure_ascii=False)
                stream.write('\n')
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        self._groups = groups

    @staticmethod
    def _current(groups, identity, revision):
        group = groups.get(identity) if isinstance(identity, str) else None
        if group is None or type(revision) is not int or revision != group['revision']:
            raise GroupConflict('The group changed. Refresh groups and try again.')
        return group

    def save(self, identity, revision, name, members, available):
        name = name.strip() if isinstance(name, str) else ''
        if not name or len(name.encode('utf-8')) > 63 or not name.isprintable():
            raise ValueError('Enter a group name of up to 63 UTF-8 bytes.')
        if not isinstance(members, list) or len(members) > 64 or any(
                not isinstance(member, str) or not DEVICE_ID.fullmatch(member) for member in members):
            raise ValueError('Choose up to 64 modules for this group.')
        members = list(dict.fromkeys(members))
        with self.lock:
            groups = self._read().copy()
            if identity is None:
                if not members:
                    raise ValueError('Select at least one discovered module to create a group.')
                if len(groups) >= 64:
                    raise ValueError('Studio supports up to 64 groups.')
                identity = secrets.token_hex(12)
                previous = {'members': [], 'revision': 0}
            else:
                previous = self._current(groups, identity, revision)
            if any(group['name'].casefold() == name.casefold() and key != identity
                   for key, group in groups.items()):
                raise ValueError('A group already uses that name.')
            if set(members) - set(previous['members']) - available:
                raise GroupConflict('New members must be discovered. Refresh modules and try again.')
            group = dict(id=identity, name=name, members=members, revision=previous['revision'] + 1)
            groups[identity] = group
            self._write(groups)
            return deepcopy(group)

    def dissolve(self, identity, revision):
        with self.lock:
            groups = self._read().copy()
            self._current(groups, identity, revision)
            del groups[identity]
            self._write(groups)


def group_list(groups):
    return sorted(groups.values(), key=lambda group: group['name'].casefold())
