# prefab.core

The `prefab.core` module handles basic file system operations and command execution.

Examples for methods in `core`:

- **cd**: cd to the given path
- **command_check**: tests if the given command is available on the system
- **command_ensure**: ensures that the given command is present, if not installs the package with the given name, which is the same as the command by default
- **command_location**: return location of cmd
- **createDir**: to create a directory
- **dir_attribs**: Updates the mode / owner / group for the given remote directory.
- **dir_ensure**: Ensures that there is a remote directory at the given location, optionally updating its mode / owner / group.
- **dir_exists**: Tells if there is a remote directory at the given location.
- **execute_python**: execute a Python script (script as content) in a remote tmux command, the stdout will be returned
- **execute_jumpscript**: execute a JumpScript (script as content) in a remote tmux command, the stdout will be returned
- **file_append**: appends the given content to the remote file at the given location
- **file_read**: read the content of a file.* file_copy: copy a file
- **file_write**: write the content to a file
- **isArch**, **isDocker**, **isMac**, **isLxc**, **isUbuntu**: check for the target os
- **run**: run a command

  ```python
  prefab.core.run('ls')
  prefab.core.run('false', die=False) #it won't raise an error
  ```

- **run_script**: run a script

  ```python
  prefab.core.run_script('cd /\npwd')
  ```

- **replace**: replace following args (when jumpscale installed it will take the args from there)

    

    ```
    - CODEDIR
    - HOSTCFGDIR
    - LOGDIR
    - BUILDDIR
    - BINDIR
    - TEMPLATEDIR
    - LIBDIR
    - DATADIR
    - BASEDIR
    - HOMEDIR
    - BASEDIRJS
    - VARDIR
    - HOSTDIR
    - JSAPPSDIR
    - CFGDIR
    - TMPDIR

    uses http://mustache.github.io/ syntax
    {{varname}}
    ```
