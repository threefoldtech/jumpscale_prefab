
from Jumpscale import j

base = j.tools.prefab._getBaseClass()


class PrefabGroup(base):

    def create(self, name, gid=None):
        """Creates a group with the given name, and optionally given gid."""
        options = []
        if gid:
            options.append("-g '%s'" % (gid))
        self.prefab.core.sudo("groupadd %s '%s'" % (" ".join(options), name))

    def check(self, name):
        """Checks if there is a group defined with the given name,
        returning its information as:
        '{"name":<str>,"gid":<str>,"members":<list[str]>}'
        or
        '{"name":<str>,"gid":<str>}' if the group has no members
        or
        'None' if the group does not exists."""
        _, data, _ = self.prefab.core.run("getent group | egrep '^%s:' ; true" % (name), die=False)
        if len(data.split(":")) == 4:
            name, _, gid, members = data.split(":", 4)
            return dict(name=name, gid=gid,
                        members=tuple(m.strip() for m in members.split(",")))
        elif len(data.split(":")) == 3:
            name, _, gid = data.split(":", 3)
            return dict(name=name, gid=gid, members=(''))
        else:
            return None

    def ensure(self, name, gid=None):
        """Ensures that the group with the given name (and optional gid)
        exists."""
        d = self.check(name)
        if not d:
            self.create(name, gid)
        else:
            if gid is not None and d.get("gid") != gid:
                self.prefab.core.sudo("groupmod -g %s '%s'" % (gid, name))

    def user_check(self, group, user):
        """Checks if the given user is a member of the given group. It
        will return 'False' if the group does not exist."""
        d = self.check(group)
        if d is None:
            return False
        else:
            return user in d["members"]

    def user_add(self, group, user):
        """Adds the given user/list of users to the given group/groups."""
        assert self.check(group), "Group does not exist: %s" % (group)
        if not self.user_check(group, user):
            self.prefab.core.sudo("usermod -a -G '%s' '%s'" % (group, user))

    def user_ensure(self, group, user):
        """Ensure that a given user is a member of a given group."""
        d = self.check(group)
        if not d:
            self.ensure("group")
            d = self.check(group)
        if user not in d["members"]:
            self.user_add(group, user)

    def user_del(self, group, user):
        """remove the given user from the given group."""
        assert self.check(group), "Group does not exist: %s" % (group)
        if self.user_check(group, user):
            cmd = "getent group | egrep -v '^%s:' | grep '%s' | awk -F':' '{print $1}' | grep -v %s; true" % (
                group, user, user)
            _, out, _ = self.prefab.core.run(cmd)
            for_user = out.splitlines()
            if for_user:
                self.prefab.core.sudo("usermod -G '%s' '%s'" % (",".join(for_user), user))
            else:
                self.prefab.core.sudo("usermod -G '' '%s'" % (user))

    def remove(self, group=None, wipe=False):
        """ Removes the given group, this implies to take members out the group
        if there are any.  If wipe=True and the group is a primary one,
        deletes its user as well.
        """
        assert self.check(group), "Group does not exist: %s" % (group)
        _, members_of_group, _ = self.prefab.core.run("getent group %s | awk -F':' '{print $4}'" % group)
        members = members_of_group.split(",")
        members = [member.split(':')[0] for member in members]
        is_primary_group = any(self.user_check(group=group, user=member) for member in members)
        if wipe:
            if len(members_of_group):
                for user in members:
                    self.user_del(group, user)
            if is_primary_group:
                self.prefab.system.user.remove(group)
            else:
                self.prefab.core.sudo("groupdel %s" % group)
        elif not is_primary_group:
            if len(members_of_group):
                for user in members:
                    self.user_del(group, user)
            self.prefab.core.sudo("groupdel %s" % group)
