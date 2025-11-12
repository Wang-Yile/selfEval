#include"testlib.h"
#include<iostream>
#include<string>

using namespace std;

static inline int f(int x){
    if(x==1)
        return 52;
    else if(x==2)
        return 27;
    else if(x==3)
        return 19;
    else if(x==4)
        return 15;
    else if(x==5)
        return 12;
    else if(x==6)
        return 11;
    else if(x==7)
        return 10;
    else if(x==8)
        return 9;
    else if(x==9)
        return 8;
    else if(x<=12)
        return 8;
    else if(x<=17)
        return 6;
    else if(x<=28)
        return 5;
    else if(x<=77)
        return 4;
    else if(x<=1325)
        return 3;
    return 2;
}

signed main(signed argc,char *argv[]){
    registerTestlibCmd(argc,argv);
    int T=inf.readInt(1,5000);
    cout<<T<<endl;
    bool ok=true;
    double pt=1;
    for(int tc=1;tc<=T;++tc){
        setTestCase(tc);
        string s=inf.readToken();
        inf.readInt(1,52);
        int k=ouf.readInt(1,52);
        int x=f((int)s.size());
        if(k<=x)
            continue;
        ok=false;
        pt=min(pt,max((double)x/k,0.1));
    }
    unsetTestCase();
    if(ok)
        quitf(_ok,"ok");
    quitp(pt,"points");
}