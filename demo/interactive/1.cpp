#include<iostream>
#include<vector>
#include<string>
#include<unordered_map>

using namespace std;

const int inf=1e9;

static inline int ask(const string &s){
    cout<<s<<endl;
    int x;
    cin>>x;
    return x;
}

int n;
string s;

int dp[55];
int pre[55];

static inline int toi(char c){
    if('A'<=c&&c<='Z')
        return c-'A';
    return c-'a'+26;
}
static inline char toc(int x){
    if(x<26)
        return x+'A';
    return x-26+'a';
}
static inline char cerydra(char c,int k){
    return toc((toi(c)+k)%52);
}
unordered_map<int,vector<int>>mp;
static inline string cerydra(const vector<int> &vec){
    mp.clear();
    int k=(int)vec.size();
    int x=pre[k],p=0;
    string ret;
    int las=0;
    for(int i=0;i<k/x;++i){
        for(int j=i*x;j<(i+1)*x;++j){
            mp[i].push_back(vec[j]);
            las=i;
            for(int t=1;t<=i;++t)
                ret.push_back(cerydra(s[p++],vec[j]));
        }
    }
    for(int i=k/x*x;i<(int)vec.size();++i){
        mp[k/x].push_back(vec[i]);
        las=k/x;
        for(int t=1;t<=k/x;++t)
            ret.push_back(cerydra(s[p++],vec[i]));
    }
    if(p<(int)s.size()){
        mp[las].pop_back();
        mp[las+(int)s.size()-p].push_back(vec.back());
        while(p<(int)s.size())
            ret.push_back(cerydra(s[p++],vec.back()));
    }
    return ret;
}

static inline void solve(){
    cin>>s;
    n=(int)s.size();
    dp[1]=1;
    for(int k=2;k<=52;++k){
        dp[k]=inf;
        for(int x=1;x<k;++x){
            int len=x*(k/x-1)*(k/x)/2+(k/x)*(k%x);
            if(len<=n){
                int w=max(dp[k%x],dp[x]);
                if(w<dp[k]){
                    pre[k]=x;
                    dp[k]=w;
                }
            }
        }
        ++dp[k];
    }
    vector<int>vec;
    for(int i=0;i<52;++i)
        vec.push_back(i);
    for(;;){
        int x=ask(cerydra(vec));
        if(x==(int)s.size())
            return;
        vec=mp[x];
        // cerr<<"\t"<<mp.size()<<endl;
        // for(auto p:mp){
        //     cerr<<"\t"<<p.first<<" |    ";
        //     for(auto x:p.second)
        //         cerr<<x<<' ';
        //     cerr<<endl;
        // }
        // cerr<<"\tpos = ";
        // for(auto x:vec)
        //     cerr<<x<<' ';
        // cerr<<endl;
        if(vec.size()<=1)
            break;
    }
    string ret;
    for(auto c:s)
        ret.push_back(cerydra(c,vec[0]));
    ask(ret);
}

signed main(){
    ios::sync_with_stdio(false);
    cin.tie(0);
    int T;
    cin>>T;
    while(T--)
        solve();
    return 0;
}