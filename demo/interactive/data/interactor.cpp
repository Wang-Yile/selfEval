#include"testlib.h"
#include<iostream>
#include<string>

using namespace std;

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

static inline string make(const string &s,int k){
    string t;
    for(auto c:s)
        t.push_back(cerydra(c,k));
    return t;
}

signed main(signed argc,char *argv[]){
    registerInteraction(argc,argv);
    int T=inf.readInt(1,5000);
    cout<<T<<endl;
    for(int tc=1;tc<=T;++tc){
        setTestCase(tc);
        string s=inf.readToken();
        int k=inf.readInt(1,52);
        cout<<make(s,k)<<endl;
        int cnt=0;
        for(;;){
            ++cnt;
            if(cnt>52)
                quitf(_wa,"cnt > 52");
            // string t=ouf.readToken();
            string t=ouf.readToken("[a-zA-Z]+");
            cerr<<"A"<<endl;
            if(s.size()!=t.size())
                quitf(_wa,"s.size() != t.size()");
            int x=0;
            for(int i=0;i<(int)s.size();++i)
                if(s[i]==t[i])
                    ++x;
            cout<<x<<endl;
            if(x==(int)s.size())
                break;
        }
        tout<<cnt<<endl;
    }
    quitf(_ok,"ok");
}