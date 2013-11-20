var Picklr = (function($, Handlebars, History) {
    // Configuration variables
    var _config = {
        PROGRESS_POLL_INTERVAL: 3000,
        ENABLE_HISTORY_LOGGING: false
    };
    // Global variables for this app
    var _globals = {
        page: 1,
        tags: [],
        syncing: false, 
        timer: null,
        ids: []
    };
    // Cached UI elements
    var _ui = {
        idInput: null,
        descriptionInput: null,
        tagInput: null,
        queryInput: null,
        metaDataForm: null,
        filterForm: null,
        status: null,
        thumbs: null,
        paging: null,
        syncNow: null, 
        viewer: null,
        viewerContainer: null,
        overlay: null,
        mainContainer: null
    };
    // Cached templates
    var _template = {
        thumb: null,
        status: null,
        paging: null,
        viewer: null
    };
    // Display an informational status
    var _showInfo = function(msg) {
        _ui.status.html('<span class="info">INFO: ' + msg + '</span>');
    };
    // Display an error status
    var _showError = function(msg) {
        _ui.status.html('<span class="error">ERROR: ' + msg + '</span>');
    };
    // Load a page of files
    var _load = function(page, query, callback) {
        _hideViewer();
        $.ajax({
            url: '/load/' + page + (($.trim(query) === '') ? '' : '?query=' + query),
            cache: false,
            dataType: 'json'
        }).done(function(data) {
            // Refresh the tag array *without reassigning the array*, 
            // otherwise tagit autocomplete stops working...
            _globals.tags.length = 0;
            [].push.apply(_globals.tags, data.tags.split('|'));
            // Buffer array to efficiently concatenate output HTML
            var output = [];
            // Reset the global array of image IDs
            _globals.ids.length = 0;
            // Create the thumbnail display
            $.each(data.files, function(i, item) {
                output.push(_template.thumb(item));
                _globals.ids.push(item.id);
            });
            _ui.thumbs.html(output.join(''));
            // Empty the output array
            output.length = 0;
            // Create the paging nav
            for(var i = 1; i <= data.total_pages; i ++) 
                output.push(_template.paging({ "n": i }));
            _ui.paging.html(_template.status(data) + ' &nbsp; ' + output.join('|'));
            // Populate the status bar
            _showInfo('Ready.');
            // If a callback function has been passed in, call it
            if(typeof callback === 'function')
                callback();
        }).fail(function(request, status, error) {
            _showError(error);
        });
    };
    var _view = function(id) {
        var link = $('#i-' + id + ' a.view-large').first();
        var html = _template.viewer({ 
            'sharekey': link.data('sharekey'),
            'path': link.data('path')
        });
        _ui.mainContainer.hide();
        _ui.overlay.show();
        _ui.viewer.html(html);
        _ui.viewerContainer.show();
        // TODO: Set the height of the overlay AFTER the image has loaded
        // _ui.overlay.height($(document).height());
    };
    var _hideViewer = function() {
        _ui.overlay.hide();
        _ui.viewerContainer.hide();
        _ui.mainContainer.show();
    };
    // Synchronise with Dropbox
    var _sync = function() {
        _ui.syncNow.html('Syncing...');
        _showInfo('Sync in progress...');
        _globals.syncing = true;
        // Start the synchronisation
        $.ajax({
            url: '/sync',
            cache: false,
            dataType: 'json'
        }).done(function(data) {
            _globals.syncing = false;
            if(data.added != 0 || data.deleted != 0)
                _showInfo(data.added + ' files added, ' + data.deleted + ' deleted. <a href="/" id="reload">Click here to reload</a>.');
            else
                _showInfo('Nothing changed.');
        }).fail(function(request, status, error) {
            _showError(error);
        }).always(function() {
            // Make sure we clear the interval which is checking progress
            clearInterval(_globals.timer);
            _ui.syncNow.html('Sync Now');
            _globals.syncing = false;
        });
        // Kick off the progress polling
        _globals.timer = setInterval(_showProgress, _config.PROGRESS_POLL_INTERVAL);
    };
    // Fetch the current number of items remaining 
    // in the sync queue for the current user
    var _showProgress = function() {
        $.get('/report-progress', function(data) {
            if(_globals.syncing)
                _showInfo('Sync in progress... ' + data.remaining + ' files remaining.');
        });
    };
    // Save metadata for an image
    var _save = function(page) {
        $.ajax({
            url: '/save',
            data: _ui.metaDataForm.serialize(),
            cache: false,
            type: 'POST',
            dataType: 'json',
        }).done(function(data) {
            // Push any new tags which were returned onto the global tag array
            [].push.apply(_globals.tags, data.newtags);
            // Update the data atributes of the edited item
            var item = $('#i-' + _ui.idInput.val()).find('a.edit-tags').first();
            item.data('tags', _ui.tagInput.val());
            item.data('description', _ui.descriptionInput.val());
            _showInfo('Saved.');
        }).fail(function(request, status, error) {
            _showError(error);
        });
    };
    // Refetch a thumbnail (in case the initial fetch failed for some reason)
    var _refetchThumbnail = function(id) {
        $.ajax({
            url: '/refetch-thumbnail',
            data: { id: id },
            cache: false,
            type: 'POST',
            dataType: 'json',
        }).done(function(data) {
            if(data.result == 1)
                _showInfo('Thumbnail updated.');
            else
                _showError('Couldn\'t retrieve thumbnail.');
            // Force-refresh the thumbnail 
            $('#i-' + id).find('a.view-large > img').first().attr('src', '/static/img/thumbs/' + id + '.jpg?r=' + new Date().getTime());
        }).fail(function(request, status, error) {
            _showError(error);
        });
    };
    // Public methods
    return {
        // Initialise the app on load
        init: function(page, file) {
            _globals.page = page;
            // Set up History.js
            History.options.debug = _config.ENABLE_HISTORY_LOGGING;
            var state = History.getState();
            History.debug('initial:', state.data, state.title, state.url);
            // Cache selectors for UI elements
            _ui.idInput = $('#fileid');
            _ui.descriptionInput = $('#description');
            _ui.tagInput = $('#tags');
            _ui.queryInput = $('#query');
            _ui.metaDataForm = $('#tag-editor');
            _ui.filterForm = $('#tag-filter');
            _ui.status = $('#status');
            _ui.thumbs = $('#thumbs');
            _ui.paging = $('#paging');
            _ui.syncNow = $('#sync-now');
            _ui.overlay = $('#overlay');
            _ui.viewer = $('#large-image');
            _ui.viewerContainer = $('#large-image-container');
            _ui.mainContainer = $('#container');
            // Compile templates
            _template.thumb = Handlebars.compile($('#thumb-template').html());
            _template.status = Handlebars.compile($('#status-template').html());
            _template.paging = Handlebars.compile($('#paging-template').html());
            _template.viewer = Handlebars.compile($('#viewer-template').html());
            // Set up tag autocomplete on the tag edit field
            _ui.tagInput.tagit({
                singleFieldDelimiter: '|',
                autocomplete: {
                    delay: 0, 
                    minLength: 2,
                    source: _globals.tags
                }
            });
            // Set up tag autocomplete on the tag query field
            _ui.queryInput.tagit({
                singleFieldDelimiter: '|',
                autocomplete: {
                    delay: 0, 
                    minLength: 2,
                    source: _globals.tags
                }
            });
            // Handle tag edit button click
            _ui.thumbs.on('click', 'a.edit-tags', function(e) {
                e.preventDefault();
                e.stopPropagation();
                var link = $(this);
                _ui.thumbs.find('div').removeClass('selected');
                link.parent().addClass('selected');
                _ui.idInput.val(link.data('fileid'));
                _ui.descriptionInput.val(link.data('description'))
                _ui.tagInput.tagit('removeAll');
                $.each(link.data('tags').split('|'), function(i, item) {
                    _ui.tagInput.tagit('createTag', item);
                });
                _ui.metaDataForm.show();
                _ui.metaDataForm.find('.tagit input[type=text]:first').focus();
            });
            // Handle thumbnail click (view large version)
            _ui.thumbs.on('click', 'a.view-large', function(e) {
                e.preventDefault();
                e.stopPropagation();
                var id = parseInt($(this).data('fileid'), 10);
                History.pushState({ page: null, image: id }, 'Image ' + id, '/file/' + id);
            });
            // Handle click on a page number link
            _ui.paging.on('click', 'a', function(e) {
                e.preventDefault();
                e.stopPropagation();
                var page = parseInt($(this).data('page'), 10);
                History.pushState({ page: page, image: null }, 'Page ' + page, '/' + page);
            });
            // Handle sync button click
            _ui.syncNow.on('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                _sync();
            });
            // Handle reload link click
            _ui.status.on('click', '#reload', function(e) {
                e.preventDefault();
                e.stopPropagation();
                _load(_globals.page, _ui.queryInput.val());
            });
            // Handle edit form submit
            _ui.metaDataForm.on('submit', function(e) {
                e.preventDefault();
                e.stopPropagation();
                _ui.metaDataForm.hide();
                _ui.thumbs.find('div').removeClass('selected');
                _save();
            });
            // Handle filter form submit
            _ui.filterForm.on('submit', function(e) {
                e.preventDefault();
                e.stopPropagation();
                _ui.metaDataForm.hide();
                _ui.thumbs.find('div').removeClass('selected');
                _globals.page = 1;
                _load(_globals.page, _ui.queryInput.val());
            });
            // Handle cancel button click
            _ui.viewerContainer.on('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                var pageId = _globals.page;
                History.pushState({ page: pageId, image: null }, 'Page ' + pageId, '/' + pageId);
            });
            // Handle cancel button click
            $('#cancel-edit').on('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                _ui.metaDataForm.hide();
                _ui.thumbs.find('div').removeClass('selected');
            });
            // Handle refetch thumbnail button click
            $('#refetch-thumbnail').on('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                var id = _ui.idInput.val();
                _refetchThumbnail(id);
            });
            // Handle user closing the window/tab
            $(window).bind('beforeunload', function () {
                // TRY(!) to stop the user leaving in the middle of a sync operation
                if (_globals.syncing) {
                    return 'A sync is currently in progress.';
                }
            });
            // Bind to History.js state change
            $(window).bind('statechange', function() {
                // Log the state
                var state = History.getState(); 
                History.debug('statechange:', state.data, state.title, state.url);
                _hideViewer();
                _ui.mainContainer.show();

                if(state.title === '') {
                    _load(1, _ui.queryInput.val());
                    _globals.page = 1;
                } else {
                    // If the state contains a page ID, load the page
                    if(state.data.page) {
                        _load(state.data.page, _ui.queryInput.val());
                        _globals.page = state.data.page;
                    } else if(state.data.image) { // If the state contains an image ID, load it
                        _view(state.data.image);
                    }
                }
            });
            // If we've got a file ID, load the viewer, then sync 
            // in the background, otherwise just sync straight away
            var callback = (file > 0) ? function() { _view(file); _sync(); } : _sync;
            // Initially load the first page and kick off our callback
            _load(_globals.page, _ui.queryInput.val(), callback);            
        },
        globals: _globals,
        ui: _ui
    }
}(jQuery, Handlebars, History));