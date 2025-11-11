from .ds import SimpleModel

class UserInteractorConf(SimpleModel):
    fast_sandbox: bool = False
    echo: bool = False
UserInteractor = UserInteractorConf()

def acquire_interactor_fast_sandbox():
    return UserInteractor.fast_sandbox
def acquire_interactor_echo():
    return UserInteractor.echo
