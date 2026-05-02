package study.langgraph.lessons.l20_course_review;

/**
 * 与 Python {@code lesson20_course_review/advancement.py} 正文对齐的进阶备忘。
 */
public final class AdvancementRoadmap {

    private AdvancementRoadmap() {
    }

    public static String formatted() {
        StringBuilder sb = new StringBuilder();
        sb.append("=== 进阶路线（建议）===\n\n");
        sb.append("【约 30 天】\n");
        for (String x : NEXT_30) {
            sb.append("  - ").append(x).append("\n");
        }
        sb.append("\n【约 60～90 天】\n");
        for (String x : DAY60_90) {
            sb.append("  - ").append(x).append("\n");
        }
        sb.append("\n说明：Streaming 全量语义见大纲第 21 课。\n");
        return sb.toString();
    }

    private static final String[] NEXT_30 = {
            "巩固：用业务域重写「生成-评估」最小闭环。",
            "观测：节点日志统一 request_id / thread_id。",
            "持久化：InMemorySaver → Sqlite/Postgres checkpointer。",
            "选修：扩展 stream_mode（第 21 课）。",
    };

    private static final String[] DAY60_90 = {
            "规模化：多租户 thread_id、配额与限流。",
            "质量：黄金套件进 CI；Capstone 质检成本预算。",
            "编排：子图边界与状态契约。",
            "治理：分环境配置与发布门禁常态化。",
    };
}
