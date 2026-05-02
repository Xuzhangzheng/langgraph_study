package study.langgraph.lessons.l18_production_governance;

import org.bsc.langgraph4j.state.AgentState;
import org.bsc.langgraph4j.state.Channel;
import org.bsc.langgraph4j.state.Channels;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 第十八课状态：与 Python {@code GovernancePipelineState}（{@code 18_production_governance_graph.py}）键名对齐。
 * <p>
 * {@link #CONTRACT_CHECK} / {@link #DEPENDENCY_LOCK_CHECK} / {@link #PREFLIGHT_CHECK} 取值为
 * {@code pending}｜{@code pass}｜{@code fail}；聚合路由在 {@code preflight_health} 之后执行。
 */
public final class L18State extends AgentState {

    /** 链路 id：对齐日志与发布工单号外的技术追踪 */
    public static final String TRACE_ID = "trace_id";
    /** {@code dev}｜{@code staging}｜{@code prod} ——决定 profile 与 pin 规则 */
    public static final String APP_ENV = "app_env";
    /** {@code llm}｜{@code fallback} */
    public static final String MODE = "mode";
    /** 发布单号（业务可读）；normalize 后仍写回同键 */
    public static final String RELEASE_ID = "release_id";
    /** 自由文本：变更说明 + 教学用 {@code FORCE_*} 关键字 */
    public static final String RELEASE_NOTES = "release_notes";
    /** {@code pending}｜{@code ok}｜{@code invalid} */
    public static final String RELEASE_GATE = "release_gate";
    /** 多行摘要：flags / log_level / pin 期望等 */
    public static final String ENV_PROFILE_SUMMARY = "env_profile_summary";
    /** 环境清单期望的契约版本（通常来自部署变量） */
    public static final String EXPECTED_CONTRACT_VERSION = "expected_contract_version";
    /** 代码内嵌对照；具体常量值见 {@link Lesson18App#STATE_CONTRACT_VERSION}（与 Python 同源）。 */
    public static final String OBSERVED_CONTRACT_VERSION = "observed_contract_version";
    /** 契约门禁结果 */
    public static final String CONTRACT_CHECK = "contract_check";
    /** profile 期望的依赖锁定指纹 */
    public static final String EXPECTED_DEPS_PIN = "expected_deps_pin";
    /** 进程环境 {@code REPO_DEPS_PIN} 的实际值 */
    public static final String OBSERVED_DEPS_PIN = "observed_deps_pin";
    /** 依赖锁定门禁 */
    public static final String DEPENDENCY_LOCK_CHECK = "dependency_lock_check";
    /** 预检门禁 */
    public static final String PREFLIGHT_CHECK = "preflight_check";
    /** 预检明细（多行） */
    public static final String PREFLIGHT_LOG = "preflight_log";
    /** LLM 或模板产出的风险叙述 */
    public static final String RISK_NARRATIVE = "risk_narrative";
    /** {@code pending}｜{@code promote}｜{@code hold}｜{@code rollback_recommend} */
    public static final String GOVERNANCE_DECISION = "governance_decision";
    /** 给人读的最终报告 */
    public static final String FINAL_REPORT = "final_report";
    /** 追加型诊断 */
    public static final String DIAGNOSTICS = "diagnostics";

    /**
     * LangGraph4j 通道定义：{@code base} 覆盖；{@code appender} 等价 Python {@code Annotated[list, operator.add]}。
     */
    public static final Map<String, Channel<?>> SCHEMA = Map.ofEntries(
            Map.entry(TRACE_ID, Channels.base(() -> "")),
            Map.entry(APP_ENV, Channels.base(() -> "dev")),
            Map.entry(MODE, Channels.base(() -> "fallback")),
            Map.entry(RELEASE_ID, Channels.base(() -> "")),
            Map.entry(RELEASE_NOTES, Channels.base(() -> "")),
            Map.entry(RELEASE_GATE, Channels.base(() -> "pending")),
            Map.entry(ENV_PROFILE_SUMMARY, Channels.base(() -> "")),
            Map.entry(EXPECTED_CONTRACT_VERSION, Channels.base(() -> "")),
            Map.entry(OBSERVED_CONTRACT_VERSION, Channels.base(() -> "")),
            Map.entry(CONTRACT_CHECK, Channels.base(() -> "pending")),
            Map.entry(EXPECTED_DEPS_PIN, Channels.base(() -> "")),
            Map.entry(OBSERVED_DEPS_PIN, Channels.base(() -> "")),
            Map.entry(DEPENDENCY_LOCK_CHECK, Channels.base(() -> "pending")),
            Map.entry(PREFLIGHT_CHECK, Channels.base(() -> "pending")),
            Map.entry(PREFLIGHT_LOG, Channels.base(() -> "")),
            Map.entry(RISK_NARRATIVE, Channels.base(() -> "")),
            Map.entry(GOVERNANCE_DECISION, Channels.base(() -> "pending")),
            Map.entry(FINAL_REPORT, Channels.base(() -> "")),
            Map.entry(DIAGNOSTICS, Channels.appender(ArrayList::new))
    );

    public L18State(Map<String, Object> init) {
        super(init);
    }

    public String traceId() {
        return value(TRACE_ID).map(Object::toString).orElse("");
    }

    public String appEnv() {
        return value(APP_ENV).map(Object::toString).orElse("dev");
    }

    public String mode() {
        return value(MODE).map(Object::toString).orElse("fallback");
    }

    public String releaseId() {
        return value(RELEASE_ID).map(Object::toString).orElse("");
    }

    public String releaseNotes() {
        return value(RELEASE_NOTES).map(Object::toString).orElse("");
    }

    public String releaseGate() {
        return value(RELEASE_GATE).map(Object::toString).orElse("pending");
    }

    public String envProfileSummary() {
        return value(ENV_PROFILE_SUMMARY).map(Object::toString).orElse("");
    }

    public String expectedContractVersion() {
        return value(EXPECTED_CONTRACT_VERSION).map(Object::toString).orElse("");
    }

    public String observedContractVersion() {
        return value(OBSERVED_CONTRACT_VERSION).map(Object::toString).orElse("");
    }

    public String contractCheck() {
        return value(CONTRACT_CHECK).map(Object::toString).orElse("pending");
    }

    public String expectedDepsPin() {
        return value(EXPECTED_DEPS_PIN).map(Object::toString).orElse("");
    }

    public String observedDepsPin() {
        return value(OBSERVED_DEPS_PIN).map(Object::toString).orElse("");
    }

    public String dependencyLockCheck() {
        return value(DEPENDENCY_LOCK_CHECK).map(Object::toString).orElse("pending");
    }

    public String preflightCheck() {
        return value(PREFLIGHT_CHECK).map(Object::toString).orElse("pending");
    }

    public String preflightLog() {
        return value(PREFLIGHT_LOG).map(Object::toString).orElse("");
    }

    public String riskNarrative() {
        return value(RISK_NARRATIVE).map(Object::toString).orElse("");
    }

    public String governanceDecision() {
        return value(GOVERNANCE_DECISION).map(Object::toString).orElse("pending");
    }

    public String finalReport() {
        return value(FINAL_REPORT).map(Object::toString).orElse("");
    }

    @SuppressWarnings("unchecked")
    public List<String> diagnostics() {
        return value(DIAGNOSTICS).map(v -> (List<String>) v).orElseGet(List::of);
    }
}
