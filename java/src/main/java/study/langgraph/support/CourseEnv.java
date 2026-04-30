package study.langgraph.support;

import io.github.cdimascio.dotenv.Dotenv;

import java.nio.file.Files;
import java.nio.file.Path;

/**
 * 与 Python {@code load_dotenv} 类似：优先读仓库根目录 {@code .env}，再退回 {@link System#getenv}。
 */
public final class CourseEnv {

    private static final Dotenv DOTENV;

    static {
        Path cwd = Path.of(System.getProperty("user.dir", ".")).toAbsolutePath().normalize();
        Path repoRoot = cwd.getFileName() != null && "java".equalsIgnoreCase(cwd.getFileName().toString())
                ? cwd.getParent()
                : cwd;
        Path envFile = repoRoot.resolve(".env");
        if (Files.isRegularFile(envFile)) {
            DOTENV = Dotenv.configure()
                    .directory(repoRoot.toString())
                    .filename(".env")
                    .ignoreIfMalformed()
                    .load();
        } else {
            DOTENV = Dotenv.configure().ignoreIfMissing().load();
        }
    }

    private CourseEnv() {
    }

    public static String get(String key, String defaultValue) {
        String v = DOTENV.get(key);
        if (v != null && !v.isBlank()) {
            return v.trim();
        }
        v = System.getenv(key);
        if (v != null && !v.isBlank()) {
            return v.trim();
        }
        return defaultValue;
    }
}
