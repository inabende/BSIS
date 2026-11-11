"""
Who can do what — the single place where project access rules live.

Every view that touches project data must go through these functions
(directly or via the mixins in ``apps.projects.mixins``), so the rules
are enforced consistently.

Rules
-----
- System admins (active superusers) can see and manage everything.
- Other users only see projects they are a member of.
- Leads manage the project's details and members.
- Leads and readers register participants and samples.
- Reviewers approve, lock and unlock final results; otherwise reviewers
  and viewers are read-only.
- While a slide is being read blind (awaiting reader 2 or a tie-breaker),
  each reading is visible only to its own reader, reviewers and system
  admins (see apps/qc/access.py).
- Closed or archived projects are read-only for everyone except system
  admins, who can still change the project's status.
"""

from .models import Project, ProjectMembership

Role = ProjectMembership.Role

DATA_ENTRY_ROLES = {Role.LEAD, Role.READER}


def visible_projects(user):
    """Projects the user is allowed to see."""
    if not user.is_authenticated:
        return Project.objects.none()
    if user.is_system_admin:
        return Project.objects.all()
    return Project.objects.filter(memberships__user=user).distinct()


def get_role(user, project):
    """The user's role in the project, or None if they aren't a member."""
    if not user.is_authenticated:
        return None
    membership = ProjectMembership.objects.filter(project=project, user=user).only("role").first()
    return membership.role if membership else None


def can_view_project(user, project):
    return user.is_authenticated and (user.is_system_admin or get_role(user, project) is not None)


def can_create_project(user):
    return user.is_authenticated and (user.is_system_admin or user.can_create_projects)


def can_manage_project(user, project):
    """Edit project details and members."""
    if not user.is_authenticated:
        return False
    if user.is_system_admin:
        return True
    return not project.is_read_only and get_role(user, project) == Role.LEAD


def can_change_status(user, project):
    """Admins can always reopen/close; leads can close an active project."""
    if not user.is_authenticated:
        return False
    return user.is_system_admin or (not project.is_read_only and get_role(user, project) == Role.LEAD)


def can_enter_data(user, project):
    """Register and edit participants and samples."""
    if not user.is_authenticated or project.is_read_only:
        return False
    if user.is_system_admin:
        return True
    return get_role(user, project) in DATA_ENTRY_ROLES


def can_review(user, project):
    """Approve, lock and unlock final results. Reviewers and system admins only (separation of duties)."""
    if not user.is_authenticated or project.is_read_only:
        return False
    return user.is_system_admin or get_role(user, project) == Role.REVIEWER


def sees_blinded_results(user, project):
    """Can see every reading even while a slide is still being read blind."""
    return user.is_authenticated and (user.is_system_admin or get_role(user, project) == Role.REVIEWER)


def project_permissions(user, project):
    """All permission flags for templates, computed once per request."""
    return {
        "role": get_role(user, project),
        "can_manage": can_manage_project(user, project),
        "can_change_status": can_change_status(user, project),
        "can_enter_data": can_enter_data(user, project),
        "can_review": can_review(user, project),
    }
