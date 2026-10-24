#include <windows.h>
#include <audioclient.h>
#include <audioclientactivationparams.h>
#include <audiopolicy.h>
#include <endpointvolume.h>
#include <mmdeviceapi.h>
#include <functiondiscoverykeys_devpkey.h>
#include <tlhelp32.h>
#include <wrl.h>
#include <wrl/implements.h>
#include <string>
#include <vector>
#include <thread>
#include <atomic>
#include <chrono>
#include <algorithm>
#include <cmath>

using namespace Microsoft::WRL;
using CaptureCallback = void(__cdecl*)(int, const void*, int, double, int, void*);
struct ComScope { HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED); ~ComScope(){ if(SUCCEEDED(hr)) CoUninitialize(); } };
static std::wstring escape(const std::wstring& s) {
    std::wstring o=L"\"";
    for(auto c:s) { if(c==L'"'||c==L'\\') { o+=L'\\';o+=c; } else if(c>=32) o+=c; }
    return o+L"\"";
}
static wchar_t* copy(const std::wstring& s){ auto p=(wchar_t*)CoTaskMemAlloc((s.size()+1)*sizeof(wchar_t)); if(p) memcpy(p,s.c_str(),(s.size()+1)*sizeof(wchar_t)); return p; }
static std::wstring processPath(DWORD pid) {
    HANDLE h=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid); if(!h)return L"";
    wchar_t p[32768]; DWORD n=32768; bool ok=QueryFullProcessImageNameW(h,0,p,&n);CloseHandle(h);return ok?std::wstring(p,n):L"";
}
static DWORD rootProcess(DWORD pid) {
    HANDLE snap=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0); if(snap==INVALID_HANDLE_VALUE)return pid;
    std::vector<PROCESSENTRY32W> list; PROCESSENTRY32W e{};e.dwSize=sizeof(e);
    if(Process32FirstW(snap,&e))do { list.push_back(e); }while(Process32NextW(snap,&e));CloseHandle(snap);
    for(int i=0;i<32;i++) {
        auto it=std::find_if(list.begin(),list.end(),[&](auto& x){return x.th32ProcessID==pid;});if(it==list.end())break;
        auto parent=std::find_if(list.begin(),list.end(),[&](auto& x){return x.th32ProcessID==it->th32ParentProcessID;});
        if(parent==list.end()||_wcsicmp(it->szExeFile,parent->szExeFile)!=0||parent->th32ProcessID==pid)break;
        pid=parent->th32ProcessID;
    }return pid;
}
extern "C" __declspec(dllexport) void __cdecl oc_free(void* p){CoTaskMemFree(p);}
extern "C" __declspec(dllexport) wchar_t* __cdecl oc_devices() {
    ComScope cs; ComPtr<IMMDeviceEnumerator> en;ComPtr<IMMDeviceCollection> collection;
    std::wstring json=L"[";bool first=true;
    if(SUCCEEDED(CoCreateInstance(__uuidof(MMDeviceEnumerator),nullptr,CLSCTX_ALL,IID_PPV_ARGS(&en)))&&SUCCEEDED(en->EnumAudioEndpoints(eRender,DEVICE_STATE_ACTIVE,&collection))) {
        UINT count=0;collection->GetCount(&count);
        for(UINT i=0;i<count;i++) { ComPtr<IMMDevice> d;ComPtr<IPropertyStore> props;LPWSTR id=nullptr;PROPVARIANT v;PropVariantInit(&v);
            if(FAILED(collection->Item(i,&d))||FAILED(d->GetId(&id)))continue;
            std::wstring name=id;
            if(SUCCEEDED(d->OpenPropertyStore(STGM_READ,&props))&&SUCCEEDED(props->GetValue(PKEY_Device_FriendlyName,&v))&&v.vt==VT_LPWSTR)name=v.pwszVal;
            if(!first)json+=L",";first=false;json+=L"{\"id\":"+escape(id)+L",\"name\":"+escape(name)+L"}";CoTaskMemFree(id);PropVariantClear(&v);
        }
    }return copy(json+L"]");
}
extern "C" __declspec(dllexport) wchar_t* __cdecl oc_sources() {
    ComScope cs;ComPtr<IMMDeviceEnumerator> en;ComPtr<IMMDeviceCollection> devices;std::wstring json=L"[";bool first=true;
    if(FAILED(CoCreateInstance(__uuidof(MMDeviceEnumerator),nullptr,CLSCTX_ALL,IID_PPV_ARGS(&en)))||FAILED(en->EnumAudioEndpoints(eRender,DEVICE_STATE_ACTIVE,&devices)))return copy(L"[]");
    struct Source{DWORD pid;float peak;};std::vector<Source> sources;UINT n=0;devices->GetCount(&n);
    for(UINT i=0;i<n;i++){ComPtr<IMMDevice>d;ComPtr<IAudioSessionManager2> mgr;ComPtr<IAudioSessionEnumerator> sessions;
        if(FAILED(devices->Item(i,&d))||FAILED(d->Activate(__uuidof(IAudioSessionManager2),CLSCTX_ALL,nullptr,&mgr))||FAILED(mgr->GetSessionEnumerator(&sessions)))continue;
        int count=0;sessions->GetCount(&count);
        for(int j=0;j<count;j++){ComPtr<IAudioSessionControl> c;ComPtr<IAudioSessionControl2> c2;ComPtr<IAudioMeterInformation> meter;DWORD pid=0;
            if(FAILED(sessions->GetSession(j,&c))||FAILED(c.As(&c2))||FAILED(c2->GetProcessId(&pid))||!pid)continue;
            AudioSessionState state; if(FAILED(c->GetState(&state))||state==AudioSessionStateExpired)continue;
            pid=rootProcess(pid);float peak=0;if(SUCCEEDED(c.As(&meter)))meter->GetPeakValue(&peak);
            auto old=std::find_if(sources.begin(),sources.end(),[&](auto& s){return s.pid==pid;});if(old==sources.end())sources.push_back({pid,peak});else old->peak=std::max(old->peak,peak);
        }
    }
    for(auto& s:sources){auto path=processPath(s.pid);auto slash=path.find_last_of(L"\\/");auto name=slash==std::wstring::npos?path:path.substr(slash+1);
        if(!first)json+=L",";first=false;json+=L"{\"pid\":"+std::to_wstring(s.pid)+L",\"name\":"+escape(name)+L",\"path\":"+escape(path)+L",\"peak\":"+std::to_wstring(s.peak)+L"}";
    }return copy(json+L"]");
}

class Activation : public RuntimeClass<RuntimeClassFlags<ClassicCom>, FtmBase, IActivateAudioInterfaceCompletionHandler> {
public:
    HANDLE done=CreateEventW(nullptr,TRUE,FALSE,nullptr);HRESULT result=E_PENDING;ComPtr<IAudioClient> client;
    ~Activation(){CloseHandle(done);}
    STDMETHOD(ActivateCompleted)(IActivateAudioInterfaceAsyncOperation* op) override {
        ComPtr<IUnknown> unk;HRESULT activation=E_FAIL;result=op->GetActivateResult(&activation,&unk);
        if(SUCCEEDED(result))result=activation;if(SUCCEEDED(result))result=unk.As(&client);SetEvent(done);return S_OK;
    }
};
struct Capture {
    HANDLE stop=CreateEventW(nullptr,TRUE,FALSE,nullptr);std::thread thread;CaptureCallback callback;void* context;
    std::atomic<bool> muted{false};
    ~Capture(){SetEvent(stop);if(thread.joinable())thread.join();CloseHandle(stop);}
    void run(DWORD pid,std::wstring device){
        ComScope cs;ComPtr<IAudioClient> client;ComPtr<IAudioCaptureClient> capture;HANDLE ready=CreateEventW(nullptr,FALSE,FALSE,nullptr);
        HRESULT hr=cs.hr;bool started=false;
        auto work=[&]()->HRESULT{
            if(FAILED(hr))return hr;
            if(pid){
                auto completion=Make<Activation>();ComPtr<IActivateAudioInterfaceAsyncOperation> op;
                AUDIOCLIENT_ACTIVATION_PARAMS ap{};ap.ActivationType=AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK;ap.ProcessLoopbackParams.TargetProcessId=pid;ap.ProcessLoopbackParams.ProcessLoopbackMode=PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE;
                PROPVARIANT pv{};pv.vt=VT_BLOB;pv.blob.cbSize=sizeof(ap);pv.blob.pBlobData=(BYTE*)&ap;
                HRESULT h=ActivateAudioInterfaceAsync(VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,__uuidof(IAudioClient),&pv,completion.Get(),&op);if(FAILED(h))return h;
                HANDLE waits[]={stop,completion->done};auto wait=WaitForMultipleObjects(2,waits,FALSE,15000);if(wait!=WAIT_OBJECT_0+1)return HRESULT_FROM_WIN32(wait==WAIT_OBJECT_0?ERROR_CANCELLED:ERROR_TIMEOUT);
                if(FAILED(completion->result))return completion->result;client=completion->client;
            }else{
                ComPtr<IMMDeviceEnumerator>en;ComPtr<IMMDevice>d;HRESULT h=CoCreateInstance(__uuidof(MMDeviceEnumerator),nullptr,CLSCTX_ALL,IID_PPV_ARGS(&en));if(FAILED(h))return h;
                h=device.empty()?en->GetDefaultAudioEndpoint(eRender,eMultimedia,&d):en->GetDevice(device.c_str(),&d);if(FAILED(h))return h;
                h=d->Activate(__uuidof(IAudioClient),CLSCTX_ALL,nullptr,&client);if(FAILED(h))return h;
            }
            WAVEFORMATEX fmt{};fmt.wFormatTag=WAVE_FORMAT_PCM;fmt.nChannels=1;fmt.nSamplesPerSec=16000;fmt.wBitsPerSample=16;fmt.nBlockAlign=2;fmt.nAvgBytesPerSec=32000;
            HRESULT h=client->Initialize(AUDCLNT_SHAREMODE_SHARED,AUDCLNT_STREAMFLAGS_LOOPBACK|AUDCLNT_STREAMFLAGS_EVENTCALLBACK|AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM|AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY,0,0,&fmt,nullptr);if(FAILED(h))return h;
            if(FAILED(h=client->GetService(IID_PPV_ARGS(&capture)))||FAILED(h=client->SetEventHandle(ready))||FAILED(h=client->Start()))return h;
            started=true;auto origin=std::chrono::steady_clock::now();callback(2,nullptr,0,0,0,context);
            HANDLE waits[]={stop,ready};std::vector<BYTE> silence;
            while(true){auto wait=WaitForMultipleObjects(2,waits,FALSE,250);if(wait==WAIT_OBJECT_0)break;
                if(pid){HANDLE process=OpenProcess(SYNCHRONIZE,FALSE,pid);if(!process)return HRESULT_FROM_WIN32(ERROR_PROCESS_ABORTED);bool dead=WaitForSingleObject(process,0)==WAIT_OBJECT_0;CloseHandle(process);if(dead)return HRESULT_FROM_WIN32(ERROR_PROCESS_ABORTED);}
                // Query even after timeout so device invalidation is surfaced during silence.
                UINT32 count=0;if(FAILED(h=capture->GetNextPacketSize(&count)))return h;
                while(count){BYTE* data=nullptr;UINT32 frames=0;DWORD flags=0;UINT64 pos=0,qpc=0;
                    if(FAILED(h=capture->GetBuffer(&data,&frames,&flags,&pos,&qpc)))return h;
                    auto end=std::chrono::duration<double>(std::chrono::steady_clock::now()-origin).count();
                    if(flags&AUDCLNT_BUFFERFLAGS_SILENT){silence.assign(frames*2,0);data=silence.data();}
                    if(!muted.load()&&frames)callback(0,data,static_cast<int>(frames*2),std::max(0.0,end-frames/16000.0),0,context);
                    capture->ReleaseBuffer(frames);if(FAILED(h=capture->GetNextPacketSize(&count)))return h;
                }
            }return S_OK;
        };
        hr=work();if(started)client->Stop();CloseHandle(ready);
        if(FAILED(hr)&&hr!=HRESULT_FROM_WIN32(ERROR_CANCELLED))callback(1,nullptr,0,0,static_cast<int>(hr),context);
    }
};
extern "C" __declspec(dllexport) void* __cdecl oc_start(DWORD pid,const wchar_t* device,CaptureCallback cb,void* context){
    if(!cb)return nullptr;auto c=new Capture();c->callback=cb;c->context=context;std::wstring d=device?device:L"";c->thread=std::thread([c,pid,d]{c->run(pid,d);});return c;
}
extern "C" __declspec(dllexport) void __cdecl oc_pause(void* handle,int paused){if(handle)static_cast<Capture*>(handle)->muted.store(paused!=0);}
extern "C" __declspec(dllexport) void __cdecl oc_stop(void* handle){delete static_cast<Capture*>(handle);}
