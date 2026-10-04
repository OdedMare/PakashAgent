"""`ScheduleService`: the facade routers and the worker talk to.

It owns no behaviour of its own. It builds the collaborators -- each owning
one concern and holding only what it needs -- and forwards every public call
to the one responsible, so the HTTP layer keeps a single entry point while
each concern stays small enough to read and test on its own.

`Scheduler` decides who works; `ChangeAgent` decides what a request means;
`audit` recomputes the countable facts. The collaborators here decide what to
remember and in what order -- which is why they, and not those, own the
repository. Every method takes the team from the caller's signed session.
"""

from app.bl.briefing import BriefingAgent
from app.bl.changes import ChangeAgent
from app.bl.learn import RuleLearner
from app.bl.planner import PlanningAgent
from app.bl.profile_service import ProfileService
from app.bl.scheduler import Scheduler
from app.bl.tools import ScheduleTools
from app.bl.schedule_service.answering import QuestionService
from app.bl.schedule_service.changing import ChangeService
from app.bl.schedule_service.constraints import ConstraintService
from app.bl.schedule_service.context import ScheduleContext
from app.bl.schedule_service.generation.builder import PeriodBuilder
from app.bl.schedule_service.generation.history import AssignmentHistory
from app.bl.schedule_service.generation.runner import GenerationRunner
from app.bl.schedule_service.generation.stepper import GenerationStepper
from app.bl.schedule_service.importing import ImportCommitter, ImportPreview
from app.bl.schedule_service.learning import CorrectionLearning
from app.bl.schedule_service.manual import ManualEditor
from app.bl.schedule_service.preferences import PreferenceService
from app.bl.schedule_service.profile_gate import ProfileGate
from app.bl.schedule_service.reader import ScheduleReader
from app.bl.schedule_service.speaking import BriefingService, WorkbookExporter


class ScheduleService:
    def __init__(
        self, repository, llm, launch=None, settings=None, sleep=None,
    ):
        context = ScheduleContext(repository)
        scheduler = Scheduler(llm)
        # Read-only tools, and the loop that runs them. `PlanningAgent` is
        # handed the tools rather than the repository, so the answering path
        # has no route to a write even by accident.
        tools = ScheduleTools(repository)
        gate = ProfileGate(repository, tools)
        history = AssignmentHistory(repository)
        stepper = GenerationStepper(context, scheduler, gate, history)

        self._reader = ScheduleReader(context)
        self._builder = PeriodBuilder(context, scheduler, gate, history, settings)
        self._stepper = stepper
        self._runner = GenerationRunner(context, stepper, launch, sleep)
        self._import_preview = ImportPreview(RuleLearner(llm))
        self._import_commit = ImportCommitter(context)
        self._manual = ManualEditor(context)
        self._changes = ChangeService(
            context, ChangeAgent(llm), ProfileService(repository)
        )
        self._constraints = ConstraintService(repository)
        self._learning = CorrectionLearning(repository, RuleLearner(llm))
        self._questions = QuestionService(
            context, PlanningAgent(llm, tools), tools
        )
        self._preferences = PreferenceService(repository)
        self._exporter = WorkbookExporter(context)
        self._briefing = BriefingService(
            context, BriefingAgent(llm), tools,
            current=self._reader.current,
            observe_quietly=self._learning.observe_quietly,
        )
        self._context = context

    # -- reading -------------------------------------------------------------

    def current(self, *args, **kwargs):
        return self._reader.current(*args, **kwargs)

    def get(self, *args, **kwargs):
        return self._reader.get(*args, **kwargs)

    def list_periods(self, *args, **kwargs):
        return self._reader.list_periods(*args, **kwargs)

    def period_at(self, *args, **kwargs):
        return self._reader.period_at(*args, **kwargs)

    def check_placement(self, *args, **kwargs):
        return self._reader.check_placement(*args, **kwargs)

    def overview(self, *args, **kwargs):
        return self._reader.overview(*args, **kwargs)

    # -- building ------------------------------------------------------------

    def generate(self, *args, **kwargs):
        return self._builder.generate(*args, **kwargs)

    def create_blank(self, *args, **kwargs):
        return self._builder.create_blank(*args, **kwargs)

    def start_generation(self, *args, **kwargs):
        return self._builder.start_generation(*args, **kwargs)

    def start_day_generation(self, *args, **kwargs):
        return self._builder.start_day_generation(*args, **kwargs)

    def generate_next(self, *args, **kwargs):
        return self._stepper.generate_next(*args, **kwargs)

    def cancel_generation(self, *args, **kwargs):
        return self._stepper.stop(*args, **kwargs)

    def queue_generation(self, *args, **kwargs):
        return self._runner.queue(*args, **kwargs)

    def generation_progress(self, *args, **kwargs):
        return self._runner.progress(*args, **kwargs)

    # -- import (D7) ---------------------------------------------------------

    def preview_import(self, team_id, files, learn_rules=True):
        return self._import_preview.preview(
            self._context.profile(team_id), files, learn_rules
        )

    def commit_import(self, *args, **kwargs):
        return self._import_commit.commit(*args, **kwargs)

    # -- the manual path (D18) -----------------------------------------------

    def assign(self, *args, **kwargs):
        return self._manual.assign(*args, **kwargs)

    def unassign(self, *args, **kwargs):
        return self._manual.unassign(*args, **kwargs)

    def clear(self, *args, **kwargs):
        return self._manual.clear(*args, **kwargs)

    def publish(self, *args, **kwargs):
        return self._manual.publish(*args, **kwargs)

    def unpublish(self, *args, **kwargs):
        return self._manual.unpublish(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return self._manual.delete(*args, **kwargs)

    # -- changing (D8/D12) ---------------------------------------------------

    def propose(self, *args, **kwargs):
        return self._changes.propose(*args, **kwargs)

    def apply(self, *args, **kwargs):
        return self._changes.apply(*args, **kwargs)

    def move(self, *args, **kwargs):
        return self._changes.move(*args, **kwargs)

    # -- constraints and history ---------------------------------------------

    def set_constraint(self, *args, **kwargs):
        return self._constraints.set_constraint(*args, **kwargs)

    def constraints(self, *args, **kwargs):
        return self._constraints.constraints(*args, **kwargs)

    def delete_constraint(self, *args, **kwargs):
        return self._constraints.delete_constraint(*args, **kwargs)

    def history(self, *args, **kwargs):
        return self._constraints.history(*args, **kwargs)

    # -- learning ------------------------------------------------------------

    def learn_from_changes(self, *args, **kwargs):
        return self._learning.learn_from_changes(*args, **kwargs)

    def observe_quietly(self, *args, **kwargs):
        return self._learning.observe_quietly(*args, **kwargs)

    # -- answering and simulating (D19/D20) ----------------------------------

    def ask(self, *args, **kwargs):
        return self._questions.ask(*args, **kwargs)

    def run_tool(self, *args, **kwargs):
        return self._questions.run_tool(*args, **kwargs)

    def simulate(self, *args, **kwargs):
        return self._questions.simulate(*args, **kwargs)

    # -- preferences (D21) ---------------------------------------------------

    def preferences(self, *args, **kwargs):
        return self._preferences.preferences(*args, **kwargs)

    def add_preference(self, *args, **kwargs):
        return self._preferences.add_preference(*args, **kwargs)

    def update_preference(self, *args, **kwargs):
        return self._preferences.update_preference(*args, **kwargs)

    def delete_preference(self, *args, **kwargs):
        return self._preferences.delete_preference(*args, **kwargs)

    # -- leaving the app, and speaking first ---------------------------------

    def workbook(self, *args, **kwargs):
        return self._exporter.workbook(*args, **kwargs)

    def brief(self, *args, **kwargs):
        return self._briefing.brief(*args, **kwargs)
