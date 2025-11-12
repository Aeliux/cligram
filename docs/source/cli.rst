Command-Line Interface
=======================

This application uses `typer <https://typer.tiangolo.com/>`_ as its command-line interface (CLI) framework.
Typer is built on top of Click and provides an easy way to create CLI applications with automatic help generation.
Key feature of typer is its extensibility. This allows to add custom functionality with plugins.

If you want to develop your own plugins for this application, please refer to the `plugin development guide <plugins.rst>`_.

All cli related codes are located in `cligram.cli <references/cligram.cli.rst>` module.

Context
-------

Cligram startup process relies on the ``typer.Context``, as it allows to share data and functions between different commands.

the ``ctx.obj`` dictionary is initialized at the first :py:func:`cligram.cli.callback`. This dictionary contains global arguments and init functions.

Arguments stored in keys like ``cligram.args:verbose``.

**Global Arguments:** ``cligram.args``

* ``config``: Path to the configuration file. (Default: ``None``)
* ``verbose``: Enable verbose output. (Default: ``False``)
* ``overrides``: Configuration overrides in key=value format. (Default: ``[]``)

**Initialization Functions:** ``cligram.init``

* ``core``: Initializes the core components. This includes loading configuration and setting up logging. it returns the loaded ``Config`` object.
* ``app``: Initializes the main application instance. it depends on the ``core`` init function to ensure that the core components are set up before creating the application instance. it returns the ``Application`` instance.
