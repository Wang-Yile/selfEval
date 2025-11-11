#include <fstream>
#include <sys/resource.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <unistd.h>

#include "sandbox.h"

static inline void setlimit(int code, rlim_t soft, rlim_t hard = 0) {
    if (hard == 0)
        hard = soft;
    rlimit limit;
    limit.rlim_cur = soft;
    limit.rlim_max = hard;
    setrlimit(code, &limit);
}
static inline time_t trans(const timeval &t) {
    return t.tv_sec * 1000000 + t.tv_usec;
}
static inline time_t trans(const rusage &x) {
    return trans(x.ru_stime) + trans(x.ru_utime);
}

pid_t pid, child_pid;
long time_limit;                          // 时间限制
long mem_limit, stack_limit, fsize_limit; // 空间限制，栈空间限制，创建文件大小限制
static inline void apply_rlimit() {
    setlimit(RLIMIT_CPU, ((rlim_t)time_limit + 999999) / 1000000);
    setlimit(RLIMIT_DATA, (rlim_t)mem_limit);
    setlimit(RLIMIT_STACK, (rlim_t)stack_limit);
    setlimit(RLIMIT_FSIZE, (rlim_t)fsize_limit);
}

time_t start_time;
int status;
rusage usage;
static inline int tracer() {
    for (;;) { // 监控子进程运行
        wait4(child_pid, &status, WUNTRACED, &usage);
        if (errno == EINTR)
            continue;
        if (trans(usage) - start_time > time_limit) {
            kill(child_pid, SIGKILL);
            return TLE | SIGKILL;
        }
        if ((usage.ru_maxrss << 10) > mem_limit) {
            kill(child_pid, SIGKILL);
            return MLE | SIGKILL;
        }
        if (WIFEXITED(status))
            return EXIT | WEXITSTATUS(status);
        if (WIFSIGNALED(status))
            return SIG | WTERMSIG(status);
        if (WIFSTOPPED(status)) {
            int sig = WSTOPSIG(status);
            // cerr << "sig " << sig << endl;
            if (sig == SIGXFSZ)
                return OLE;
            else if (sig == SIGXCPU)
                return TLE;
            else if (sig == SIGCONT)
                ;
            else if (WIFSIGNALED(sig))
                return SIG | sig;
            else if (WIFEXITED(sig))
                return EXIT | sig;
        }
    }
}

int main(int argc, char *argv[]) {
    pid = fork();
    char *prog_path = argv[1];
    char *output = argv[2];
    time_limit = atol(argv[3]);
    mem_limit = atol(argv[4]);
    stack_limit = atol(argv[5]);
    fsize_limit = atol(argv[6]);
    // argv[7] 是 cpuset 的二进制掩码
    int file_cnt = atoi(argv[8]);
    int args_st = 9 + (file_cnt << 1);
    itimerval it;
    it.it_value.tv_sec = time_limit / 1000000;
    it.it_value.tv_usec = time_limit % 1000000;
    it.it_interval.tv_sec = it.it_interval.tv_usec = 0;
    struct sigaction sa;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;
    if (pid == 0) {
        pid = getpid();
        char **args = new char *[argc - args_st + 2];
        args[0] = prog_path;
        for (int i = args_st; i < argc; ++i)
            args[i - args_st + 1] = argv[i];
        args[argc - args_st + 1] = nullptr;
        cpu_set_t mask;
        CPU_ZERO(&mask);
        for (int i = 0; argv[7][i]; ++i)
            if (argv[7][i] == '1')
                CPU_SET(i, &mask);
        sched_setaffinity(pid, sizeof(mask), &mask);
        kill(pid, SIGSTOP);
        apply_rlimit();
        execv(prog_path, args);
        perror("execv");
        delete[] args;
        return 128;
    } else if (pid > 0) {
        child_pid = pid;
        pid = getpid();
        it.it_value.tv_sec += 1;
        sa.sa_handler = [](int sig) {
            if (sig == SIGALRM && child_pid > 0)
                kill(child_pid, SIGKILL);
        };
        sigaction(SIGALRM, &sa, nullptr);
        wait4(child_pid, &status, WUNTRACED, &usage);
        start_time = trans(usage);
        kill(pid, SIGSTOP); // 挂起等待进一步指令
        kill(child_pid, SIGCONT);
        setitimer(ITIMER_REAL, &it, nullptr);
        int ret = tracer();
        std::ofstream out(output, std::ios::out);
        out << trans(usage) - start_time << '\n';
        out << (usage.ru_maxrss << 10) << '\n';
        out << ret << '\n';
        out.close();
        return 0;
    } else
        return 128;
}