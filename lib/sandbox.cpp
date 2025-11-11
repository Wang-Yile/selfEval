/*
sandbox.cpp

时间单位是微秒，空间单位是字节。
*/

#include <fcntl.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <poll.h>
#include <regex>
#include <seccomp.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <string>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/reg.h>
#include <sys/resource.h>
#include <sys/signalfd.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <sys/user.h>
#include <sys/wait.h>
#include <unistd.h>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace fs = std::filesystem;

using std::cerr;
using std::endl;

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

#define TRUNK 128
std::string read_string(long addr) {
    std::string result;
    char buffer[TRUNK];
    struct iovec local_iov = {
        .iov_base = buffer,
        .iov_len = TRUNK,
    };
    struct iovec remote_iov = {
        .iov_base = nullptr,
        .iov_len = TRUNK,
    };
    for (;;) {
        remote_iov.iov_base = (void *)addr;
        ssize_t bytes_read = process_vm_readv(child_pid, &local_iov, 1, &remote_iov, 1, 0);
        if (bytes_read < 0) {
            if (result.empty()) {
                throw std::system_error(errno, std::system_category(), "Failed to read process memory");
            } else {
                break;
            }
        } else if (bytes_read == 0)
            break;
        int null_pos = -1;
        for (int i = 0; i < bytes_read; ++i)
            if (buffer[i] == '\0') {
                null_pos = i;
                break;
            }
        if (null_pos == -1) {
            result.append(buffer, buffer + TRUNK);
            addr += bytes_read;
        } else {
            result.append(buffer, buffer + null_pos);
            break;
        }
    }
    return result;
}
#undef TRUNK
fs::path child_dirfd_path;
typedef std::pair<dev_t, ino64_t> identity_t;
const identity_t identity_null{-1, -1};
struct hs_type {
    inline size_t operator()(const std::pair<identity_t, std::string> &x) const {
        return x.first.second;
    }
    inline size_t operator()(const std::pair<std::string, int> &x) const {
        return (size_t)(&x.first);
    }
};
std::unordered_map<std::pair<identity_t, std::string>, int, hs_type> files_permission;
struct {
    int active;
    fs::path p, ori;
    std::string msg;
    int acc, permitted;
} trace_file_operation;
static inline identity_t get_identity(const fs::path &path) {
    struct stat64 st;
    if (stat64(path.c_str(), &st) == -1)
        return identity_null;
    return {st.st_dev, st.st_ino};
}
static inline void add_permission(const fs::path &path, int acc) {
    ++acc;
    // cerr << "add permission(" << acc << ") " << path << endl;
    if (auto id = get_identity(fs::canonical(path.parent_path())); id != identity_null)
        files_permission[{id, path.filename()}] |= acc;
}
std::unordered_set<std::string> _is_permitted_cache[4];
static inline bool _is_permitted(const fs::path &path, int acc, bool trace_on_prohibition) {
    ++acc;
    if (_is_permitted_cache[acc].count(path))
        return true;
    int permitted = 0;
    for (auto p = fs::canonical(path.parent_path()) / path.filename();;) {
        auto id = get_identity(p.parent_path());
        if (auto it = files_permission.find({id, p.filename()}); it != files_permission.end()) {
            if ((acc & it->second) == acc) { // 越权访问
                _is_permitted_cache[acc].insert(path);
                return true;
            }
            permitted |= it->second;
        }
        auto nxt = p.parent_path();
        if (p == nxt)
            break;
        p = nxt;
    }
    // 无权限
    cerr << "not permitted: " << path << endl;
    if (trace_on_prohibition) { // 显示详细调试信息
        auto p = fs::canonical(path.parent_path()) / path.filename();
        trace_file_operation.active = 1;
        trace_file_operation.p = p;
        trace_file_operation.ori = path;
        trace_file_operation.msg.clear();
        trace_file_operation.acc = acc - 1;
        trace_file_operation.permitted = permitted - 1;
    }
    return false;
}
const std::regex pattern_pipe("(^pipe:\\[\\d+\\]$)");
static inline bool is_permitted(const fs::path &path, int acc, bool trace_on_prohibition) {
    if (fs::is_symlink(path))
        return _is_permitted(path, acc, trace_on_prohibition);
    // cerr << "check " << acc << " on " << path << endl;
    fs::file_status status = fs::status(path);
    if (fs::is_fifo(status)) { // 命名管道
        trace_file_operation.msg = "fifo";
    } else if (fs::is_socket(status)) { // 套接字
        trace_file_operation.msg = "socket";
    } else if (fs::is_block_file(status)) { // 块设备
        return _is_permitted(path, acc, trace_on_prohibition);
    } else if (fs::is_character_file(status)) { // 字符设备
        return _is_permitted(path, acc, trace_on_prohibition);
    } else if (fs::is_regular_file(status)) { // 普通文件
        return _is_permitted(path, acc, trace_on_prohibition);
    } else if (fs::is_directory(status)) { // 目录
        return _is_permitted(path, acc, trace_on_prohibition);
    } else if (!fs::exists(path)) {
        if (std::regex_match(path.filename().string(), pattern_pipe)) {
            // 匿名管道，格式为 pipe:[123456]
            // 由于没有批准子进程创建管道，一般由父进程传递，可以批准
            // 这样可能造成错误判断，要求文件名不含冒号
            return true;
        }
        return _is_permitted(path, acc, trace_on_prohibition);
    } else {
        trace_file_operation.msg = "other";
    }
    if (trace_on_prohibition) {
        trace_file_operation.active = 2;
        trace_file_operation.p.clear();
        trace_file_operation.ori = path;
        // trace_file_operation.msg = "";
        trace_file_operation.acc = acc;
        trace_file_operation.permitted = 0;
    }
    return false;
}
static inline bool check_fd_operation(int fd, int acc, bool trace_on_prohibition = true) {
    try {
        return is_permitted(fs::absolute(fs::read_symlink(child_dirfd_path / std::to_string(fd))), acc, trace_on_prohibition);
    } catch (const fs::filesystem_error &e) {
        cerr << e.what() << endl;
        return false;
    }
}
static inline bool check_file_operation(long addr, int acc, bool trace_on_prohibition = true) {
    return is_permitted(fs::absolute(fs::path(read_string(addr)).lexically_normal()), acc, trace_on_prohibition);
}
static inline bool check_file_operation_at(int dirfd, long addr, int acc, bool trace_on_prohibition = true) {
    fs::path path = read_string(addr);
    if (path.is_absolute())
        return is_permitted(path, acc, trace_on_prohibition);
    if (dirfd == AT_FDCWD) // dirfd = 4294967196 时
        return is_permitted(fs::absolute(path), (int)acc, trace_on_prohibition);
    try {
        return is_permitted(fs::absolute(fs::read_symlink(child_dirfd_path / std::to_string(dirfd)) / path), acc, trace_on_prohibition);
    } catch (const fs::filesystem_error &e) {
        cerr << e.what() << endl;
        return false;
    }
}
static inline bool check_ioctl(int fd, unsigned long request) {
    // 只允许访问终端或被授权的文件
    if (check_fd_operation(fd, -1, false))
        return true;
    return _IOC_DIR(request) == _IOC_NONE || _IOC_DIR(request) == _IOC_READ;
}

#define BPF_ALLOW(x)                                \
    BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (x), 0, 1), \
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW)
static inline int install_filter_raw() {
    struct sock_filter filter[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        // 常用操作
        BPF_ALLOW(SYS_read),
        BPF_ALLOW(SYS_write),
        BPF_ALLOW(SYS_close),
        BPF_ALLOW(SYS_lseek),
        BPF_ALLOW(SYS_brk), // 调整堆大小
        // 文件操作
        BPF_ALLOW(SYS_pread64),
        BPF_ALLOW(SYS_pwrite64),
        BPF_ALLOW(SYS_readv),
        BPF_ALLOW(SYS_writev),
        BPF_ALLOW(SYS_preadv),
        BPF_ALLOW(SYS_pwritev),
        BPF_ALLOW(SYS_preadv2),
        BPF_ALLOW(SYS_pwritev2),
        // 内存管理
        BPF_ALLOW(SYS_mmap),   // 内存映射
        BPF_ALLOW(SYS_munmap), // 取消内存映射
        BPF_ALLOW(SYS_msync),  // 内存同步到磁盘
        BPF_ALLOW(SYS_fsync),
        BPF_ALLOW(SYS_mprotect), // 内存保护
        BPF_ALLOW(SYS_mremap),   // 重新映射内存
        BPF_ALLOW(SYS_madvise),  // 内存建议
        // 文件系统操作
        BPF_ALLOW(SYS_access),
        BPF_ALLOW(SYS_stat),
        BPF_ALLOW(SYS_lstat),
        BPF_ALLOW(SYS_statfs),
        BPF_ALLOW(SYS_fstat),
        // 其它
        BPF_ALLOW(SYS_getpid),
        BPF_ALLOW(SYS_gettid),
        BPF_ALLOW(SYS_getcwd),
        BPF_ALLOW(SYS_tgkill),
        BPF_ALLOW(SYS_arch_prctl),
        // 系统
        BPF_ALLOW(SYS_sendmsg),
        BPF_ALLOW(SYS_exit),
        BPF_ALLOW(SYS_exit_group),
        // 默认
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_USER_NOTIF),
        // BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_LOG),
    };
    struct sock_fprog prog = {
        .len = sizeof(filter) / sizeof(filter[0]),
        .filter = filter,
    };
    // cerr << "BPF: " << prog.len << " instructions" << endl;
    prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0);
    return (int)syscall(__NR_seccomp, SECCOMP_SET_MODE_FILTER, SECCOMP_FILTER_FLAG_NEW_LISTENER, &prog);
}
static inline int install_signalfd() {
    sigset_t mask;
    sigemptyset(&mask);
    sigaddset(&mask, SIGCHLD);
    sigprocmask(SIG_BLOCK, &mask, NULL);
    return signalfd(-1, &mask, SFD_NONBLOCK);
}
static inline void send_fd(int socket, int fd) {
    struct cmsghdr *cmsg;
    char buf[CMSG_SPACE(sizeof(fd))];
    char dummy = '!';
    struct iovec io = {
        .iov_base = &dummy,
        .iov_len = 1};
    struct msghdr msg{
        .msg_name = nullptr,
        .msg_namelen = 0,
        .msg_iov = &io,
        .msg_iovlen = 1,
        .msg_control = buf,
        .msg_controllen = sizeof(buf),
        .msg_flags = 0,
    };
    cmsg = CMSG_FIRSTHDR(&msg);
    cmsg->cmsg_level = SOL_SOCKET;
    cmsg->cmsg_type = SCM_RIGHTS;
    cmsg->cmsg_len = CMSG_LEN(sizeof(fd));
    memcpy(CMSG_DATA(cmsg), &fd, sizeof(fd));
    sendmsg(socket, &msg, 0);
}
static inline int recv_fd(int socket) {
    struct cmsghdr *cmsg;
    char buf[CMSG_SPACE(sizeof(int))];
    char dummy;
    struct iovec io = {
        .iov_base = &dummy,
        .iov_len = 1};
    struct msghdr msg{
        .msg_name = nullptr,
        .msg_namelen = 0,
        .msg_iov = &io,
        .msg_iovlen = 1,
        .msg_control = buf,
        .msg_controllen = sizeof(buf),
        .msg_flags = 0,
    };
    if (recvmsg(socket, &msg, 0) < 0)
        return -1;
    cmsg = CMSG_FIRSTHDR(&msg);
    if (cmsg && cmsg->cmsg_level == SOL_SOCKET &&
        cmsg->cmsg_type == SCM_RIGHTS) {
        int fd;
        memcpy(&fd, CMSG_DATA(cmsg), sizeof(fd));
        return fd;
    }
    return -1;
}

bool child_execved;
static inline bool handle_syscall(int syscall, unsigned long long args[]) {
    switch (syscall) {
    case SYS_openat:
        return check_file_operation_at((int)args[0], args[1], args[2] & O_ACCMODE);
    case SYS_rt_sigprocmask:
    case SYS_setitimer:
    case SYS_getitimer:
        return true;
    case SYS_execve: {
        if (child_execved)
            return false;
        child_execved = true;
        return true;
    }
    default: {
        return true;
        // cerr << "\033[31;1mdeny\033[0m " << syscall << endl;
        // return false;
    }
    }
}
static inline int tracer(int listener_fd, int signal_fd) {
    struct seccomp_notif *notif;
    struct seccomp_notif_resp *resp;
    struct seccomp_notif_sizes sizes;
    syscall(SYS_seccomp, SECCOMP_GET_NOTIF_SIZES, 0, &sizes);
    notif = (struct seccomp_notif *)malloc(sizes.seccomp_notif);
    resp = (struct seccomp_notif_resp *)malloc(sizes.seccomp_notif_resp);
    kill(child_pid, SIGCONT);
    struct pollfd pfds[2]{
        {.fd = listener_fd, .events = POLLIN | POLLPRI, .revents = 0},
        {.fd = signal_fd, .events = POLLIN | POLLPRI, .revents = 0}};
    int ret = 0;
    for (;;) {
        int poll_result = poll(pfds, 2, -1);
        if (poll_result < 0) {
            if (errno == EINTR)
                continue;
            perror("poll failed");
            ret = -1;
            break;
        }
        if (pfds[1].revents & (POLLIN | POLL_PRI)) {
            struct signalfd_siginfo siginfo;
            ssize_t s = read(signal_fd, &siginfo, sizeof(siginfo));
            if (s == sizeof(siginfo)) {
                if (siginfo.ssi_signo == SIGCHLD) {
                    if (siginfo.ssi_code == CLD_EXITED || siginfo.ssi_code == CLD_KILLED || siginfo.ssi_code == CLD_DUMPED)
                        break;
                } else
                    cerr << "Received signal " << siginfo.ssi_signo << endl;
            } else
                cerr << "Failed to read from signalfd" << endl;
        }
        if (pfds[0].revents & (POLLIN | POLL_PRI)) {
            memset(notif, 0, sizes.seccomp_notif);
            memset(resp, 0, sizes.seccomp_notif_resp);
            if (ioctl(listener_fd, SECCOMP_IOCTL_NOTIF_RECV, notif) < 0) {
                if (errno == EINTR)
                    continue;
                perror("seccomp receive failed");
                ret = -1;
                break;
            }
            resp->id = notif->id;
            if (handle_syscall(notif->data.nr, notif->data.args)) {
                resp->flags = SECCOMP_USER_NOTIF_FLAG_CONTINUE;
                resp->val = 0;
                resp->error = 0;
            } else {
                // 软拦截
                // resp->flags = 0;
                // resp->val = -1;
                // resp->error = -EPERM;
                // 硬拦截
                kill(child_pid, SIGKILL);
                ret = FBD | notif->data.nr;
                break;
            }
            if (ioctl(listener_fd, SECCOMP_IOCTL_NOTIF_SEND, resp) < 0) {
                perror("seccomp send failed");
                ret = -1;
                break;
            }
        }
    }
    free(notif);
    free(resp);
    return ret;
}

time_t start_time;
int status;
rusage usage;

int main(int argc, char *argv[]) {
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
    int socket_pair[2];
    socketpair(AF_UNIX, SOCK_STREAM, 0, socket_pair);
    pid = fork();
    if (pid == 0) {
        pid = getpid();
        char **args = new char *[argc - args_st + 2];
        args[0] = prog_path;
        for (int i = args_st; i < argc; ++i)
            args[i - args_st + 1] = argv[i];
        args[argc - args_st + 1] = nullptr;
        sa.sa_handler = [](int sig) {
            if (sig == SIGALRM && pid > 0)
                kill(pid, SIGKILL);
        };
        sigaction(SIGALRM, &sa, nullptr);
        cpu_set_t mask;
        CPU_ZERO(&mask);
        for (int i = 0; argv[7][i]; ++i)
            if (argv[7][i] == '1')
                CPU_SET(i, &mask);
        sched_setaffinity(pid, sizeof(mask), &mask);
        apply_rlimit();
        send_fd(socket_pair[1], install_filter_raw());
        tgkill(getpid(), gettid(), SIGSTOP);
        setitimer(ITIMER_PROF, &it, nullptr);
        execv(prog_path, args);
        perror("execv failed");
        delete[] args;
        return 128;
    } else if (pid > 0) {
        child_pid = pid;
        pid = getpid();
        add_permission("/etc/ld.so.preload", 0);
        add_permission("/etc/ld.so.cache", 0);
        add_permission("/lib", 0);
        add_permission("/usr/lib", 0);
        add_permission("/dev/random", 0);
        add_permission("/dev/urandom", 0);
        add_permission("/dev/null", 0);
        add_permission("/etc/localtime", 0);
        if (char *p = ttyname(stdin->_fileno); p != nullptr)
            add_permission(p, 0);
        if (char *p = ttyname(stdout->_fileno); p != nullptr)
            add_permission(p, 1);
        if (char *p = ttyname(stderr->_fileno); p != nullptr)
            add_permission(p, 1);
        for (int i = 0; i < file_cnt; ++i)
            add_permission(fs::path(argv[9 + (i << 1)]).lexically_normal(), atoi(argv[9 + (i << 1 | 1)]));
        it.it_value.tv_sec += 1;
        sa.sa_handler = [](int sig) {
            if (sig == SIGALRM && child_pid > 0)
                kill(child_pid, SIGKILL);
        };
        sigaction(SIGALRM, &sa, nullptr);
        child_dirfd_path = fs::path("/proc/" + std::to_string(child_pid) + "/fd/");
        wait4(child_pid, &status, WUNTRACED, &usage);
        start_time = trans(usage);
        kill(pid, SIGSTOP); // 挂起等待进一步指令
        int signal_fd = install_signalfd();
        int listener_fd = recv_fd(socket_pair[0]);
        setitimer(ITIMER_REAL, &it, nullptr);
        int ret = tracer(listener_fd, signal_fd);
        if (ret == -1)
            return 1;
        if (wait4(child_pid, &status, WUNTRACED, &usage) == child_pid) {
            if (!ret) {
                if (WIFEXITED(status))
                    ret = EXIT | WEXITSTATUS(status);
                else if (WIFSIGNALED(status)) {
                    int sig = WTERMSIG(status);
                    if (sig == SIGXCPU)
                        ret = TLE;
                    else if (sig == SIGXFSZ)
                        ret = OLE;
                    else
                        ret = SIG | WTERMSIG(status);
                } else
                    ret = -1;
            }
        } else {
            perror("waitpid failed");
            ret = -1;
        }
        close(signal_fd);
        close(listener_fd);
        if (ret == -1)
            return 1;
        std::ofstream out(output, std::ios::out);
        out << trans(usage) - start_time << '\n';
        out << (usage.ru_maxrss << 10) << '\n';
        out << ret << '\n';
#ifndef TINY
        if (trace_file_operation.active == 1) {
            out << "not permitted(acc=" << trace_file_operation.acc << "  permitted=" << trace_file_operation.permitted << "): " << trace_file_operation.ori;
            if (trace_file_operation.ori != trace_file_operation.p)
                out << " (aka " << trace_file_operation.ori << ")";
            out << '\n';
        } else if (trace_file_operation.active == 2) {
            out << "not permitted(acc=" << trace_file_operation.acc << "): " << trace_file_operation.ori << '\n';
            out << trace_file_operation.msg << '\n';
        }
#endif
        out.close();
        return 0;
    }
    return 128;
}