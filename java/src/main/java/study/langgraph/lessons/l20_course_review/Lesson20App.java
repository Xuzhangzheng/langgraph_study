package study.langgraph.lessons.l20_course_review;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

/**
 * 第二十课入口：打印课表 + 进阶路线；可选校验仓库根目录下 Python 主 artifact 是否存在。
 * <p>完整回归以 Python {@code python -m lesson20_course_review --verify} 为准。</p>
 */
public final class Lesson20App {

    private Lesson20App() {
    }

    static Path resolveRepoRoot() {
        Path cwd = Path.of(System.getProperty("user.dir", ".")).toAbsolutePath().normalize();
        if (cwd.getFileName() != null && "java".equalsIgnoreCase(cwd.getFileName().toString())) {
            return cwd.getParent();
        }
        return cwd;
    }

    static boolean artifactsPresent(Path root) {
        boolean all = true;
        for (CourseCatalog.LessonRow row : CourseCatalog.lessons()) {
            Path p = root.resolve(row.artifact());
            boolean ok = "lesson19_support_desk".equals(row.artifact())
                    ? Files.isDirectory(p)
                    : Files.isRegularFile(p);
            if (!ok) {
                System.out.println("[artifact-missing] " + row.artifact());
                all = false;
            }
        }
        return all;
    }

    public static void main(String[] args) {
        boolean verify = args.length > 0 && "--verify".equals(args[0].toLowerCase(Locale.ROOT));

        System.out.println("第二十课：课程复盘与进阶路线（LangGraph4j 旁路工具）");
        System.out.println("=".repeat(60));
        for (CourseCatalog.LessonRow row : CourseCatalog.lessons()) {
            System.out.printf("%2d. %s → %s%n", row.no(), row.title(), row.artifact());
            System.out.println("    要点: " + String.join(", ", row.keywords()));
        }
        System.out.println();
        System.out.println(AdvancementRoadmap.formatted());

        if (verify) {
            Path root = resolveRepoRoot();
            System.out.println("[verify] repoRoot=" + root);
            boolean ok = artifactsPresent(root);
            System.out.println(ok ? "[verify] artifacts OK" : "[verify] artifacts FAIL");
            System.exit(ok ? 0 : 1);
        }

        System.out.println("对照 Python：python -m lesson20_course_review [--mmd] [--verify]");
    }
}
