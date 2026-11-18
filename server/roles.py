"""Administrator roles and what each one may reach.

One administrator used to be all there was: `users.role` held either
'customer' or 'admin', and the whole console answered to that single string.
That works until a studio has a support person who should answer tickets but
must not touch refunds, or a sales person who should see requests but not
customers' payment records.

This module is the answer to "let the system hand out the permissions":

    owner      everything, and the only role that can make other admins
    support    conversations, and the customer context they need
    sales      project requests, orders, refunds, the catalog
    content    the website text, products, articles
    analyst    reads reports; writes nothing

A role is stored on the user as `admin_role`. The five permission groups below
are coarse on purpose: a per-checkbox matrix looks more powerful and is far
harder to reason about, and every extra switch is one more way to leave an
account able to see something it should not.

The one rule that is not a permission is the owner. There can be exactly one,
because the account that can make and unmake every other administrator has to
be the one whose recovery path is known. If the owner's password is lost, a
local command restores it - see ``server/provision_admin.py`` - and that is
deliberately something only somebody with shell access to the server can do.

Nothing here is decorative: ``can()`` is called by the request handler on every
admin route, and the console hides what the role cannot use.
"""
from __future__ import annotations

# The order matters: it is the order the console lists them in, and the first
# entry is the role a new administrator gets if none is named.
ADMIN_ROLES = ('owner', 'support', 'sales', 'content', 'analyst')

ROLE_LABELS = {
    'owner': 'Owner',
    'support': 'Support agent',
    'sales': 'Sales agent',
    'content': 'Content editor',
    'analyst': 'Analyst',
}

ROLE_SUMMARIES = {
    'owner': 'Full control, including who else is an administrator.',
    'support': 'Support conversations and the customer record they need.',
    'sales': 'Project requests, refunds and the product catalog.',
    'content': 'Website text, products and articles.',
    'analyst': 'Reads the reports. Cannot change anything.',
}

# The permission groups. Every admin route names one of these.
PERMISSIONS = (
    'support',      # tickets: read, reply, change status
    'customers',    # the customer directory and the profile detail
    'sales',        # orders, refunds, the work queue
    'catalog',      # products, categories, brands
    'content',      # website settings, hero copy, articles
    'activity',     # the audit log
    'admins',       # managing other administrators - owner only
)

GRANTS = {
    'owner': set(PERMISSIONS),
    'support': {'support', 'customers', 'activity'},
    'sales': {'sales', 'customers', 'catalog', 'activity'},
    'content': {'catalog', 'content'},
    'analyst': {'activity'},
}

# Shown in the console beside each role so an operator can see, before they
# create the account, exactly what it will be able to open.
ROLE_GRANTS_TEXT = {
    'owner': 'Everything, including administrators.',
    'support': 'Support, customers, activity.',
    'sales': 'Requests, refunds, customers, catalog, activity.',
    'content': 'Website, products, articles.',
    'analyst': 'Activity only, read-only.',
}


def normalise_role(value) -> str | None:
    """Return a known role, or None for anything else."""
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    return text if text in GRANTS else None


def can(role, permission: str) -> bool:
    """Is this administrator role allowed to touch this group?"""
    return permission in GRANTS.get(role or '', set())


def permissions_for(role) -> list[str]:
    """The groups a role may use, in a stable order for the console."""
    return [p for p in PERMISSIONS if can(role, p)]


def is_admin(user) -> bool:
    """Is this account an administrator of any kind?

    ``users.role`` keeps its original two values, so an existing deployment
    needs no data migration: an admin is anyone whose role is 'admin' and who
    carries a known ``admin_role``. A row with no admin_role - every account
    that existed before this file - is treated as the owner, because that is
    exactly what it was.
    """
    if not user:
        return False
    if user.get('role') != 'admin':
        return False
    return True


def role_of(user) -> str:
    """The effective admin role. Missing or unknown values become 'owner'."""
    if not user:
        return ''
    if user.get('role') != 'admin':
        return ''
    stored = user.get('admin_role')
    return normalise_role(stored) or 'owner'


def can_user(user, permission: str) -> bool:
    if not is_admin(user):
        return False
    return can(role_of(user), permission)


def permissions_of(user) -> list[str]:
    if not is_admin(user):
        return []
    return permissions_for(role_of(user))


def may_manage_admins(user) -> bool:
    return can_user(user, 'admins')
