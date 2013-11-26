function linearSearch(a, v) {
    for(var x=0; x<a.length; x++) {
        if(a[x][0] == v) return x;
    }
    return -1; // Value not found
}
            
function binarySearch(a, v) {
    var high = a.length - 1;
    var low = 0;
                    
    while(low <= high)
    {
        mid = parseInt((low + high) / 2);
        if(a[mid] == v) return mid;
        else if(a[mid] > v) high = (mid - 1); // Search lower values
        else if(a[mid] < v) low = (mid + 1); // Search upper values
    }
    
    return -1; // Value not found
}

var Picklr = (function($, Handlebars, History) {
    // Configuration variables
    var _config = {
        PAGE_SIZE: 20,
        PROGRESS_POLL_INTERVAL: 3000,
        ENABLE_HISTORY_LOGGING: false
    };
    // Global variables for this app
    var _globals = {
        page: 1,
        tags: [],
        syncing: false, 
        timer: null,
        index: null,
        data: []
    };
    // Cached UI elements
    var _ui = {
        idInput: null,
        descriptionInput: null,
        tagInput: null,
        queryInput: null,
        metaDataForm: null,
        filterForm: null,
        statusMessage: null,
        thumbs: null,
        pagingInfo: null,
        pagingPages: null,
        pagingPrev: null,
        pagingNext: null,
        syncNow: null, 
        viewer: null,
        viewerContainer: null,
        overlay: null,
        mainContainer: null,
        viewerPrev: null,
        viewerNext: null
    };
    // Cached templates
    var _template = {
        thumb: null,
        pagingInfo: null,
        pagingPage: null,
        pagingPrev: null,
        pagingNext: null,
        viewer: null,
        infoMessage: null,
        errorMessage: null
    };
    // Display an informational status
    var _showInfo = function(msg) {
        _ui.statusMessage.html(_template.infoMessage({ 'message': msg }));
    };
    // Display an error status
    var _showError = function(msg) {
        _ui.statusMessage.html(_template.errorMessage({ 'message': msg }));
    };
    // Get paging information
    var _getPagingInfo = function () {
        var totalFiles = _globals.data.length;
        return {
            currentPage: _globals.page,
            totalFiles: totalFiles,
            totalPages: Math.ceil(totalFiles / _config.PAGE_SIZE)
        };
    };
    var _populatePagination = function(data) {
        // Buffer array to efficiently concatenate output HTML
        var output = [];
        for(var i = 1; i <= data.totalPages; i ++) 
            output.push(_template.pagingPage({ "n": i }));
        _ui.pagingPages.html(output.join('|'));
    };
    var _page = function(page) {
        // Buffer array to efficiently concatenate output HTML
        var output = [];
        _globals.page = page;
        var pinfo = _getPagingInfo();
        _ui.pagingInfo.html(_template.pagingInfo(pinfo));
        var start = ((_globals.page - 1) * _config.PAGE_SIZE);
        var end = start + _config.PAGE_SIZE;
        if(end > _globals.data.length)
            end = _globals.data.length;
        // Create the thumbnail display for the first page
        for(var i=start; i<end; i++) {
            output.push(_template.thumb({ id: _globals.data[i][0] }));
        }
        _ui.thumbs.html(output.join(''));
        // Create prev/next links
        var totalPages = Math.ceil(_globals.data.length / _config.PAGE_SIZE);
        _ui.pagingPrev.html(_template.pagingPrev({ 'n': ((_globals.page > 1) ? (_globals.page - 1) : 0) }));
        _ui.pagingNext.html(_template.pagingNext({ 'n': ((_globals.page < totalPages) ? (_globals.page + 1) : 0) }));
    };
    var _search = function(query, callback) {
        $.ajax({
            url: '/search?q=' + query,
            cache: false,
            type: 'GET',
            dataType: 'json',
        }).done(function(data) {
            
            // If a callback function has been passed in, call it
            if(typeof callback === 'function')
                callback();         
        }).fail(function(request, status, error) {
            _showError(error);
        });
    };
    var _loadFiles = function(callback) {
        $.ajax({
            url: '/load-files',
            cache: false,
            type: 'GET',
            dataType: 'json',
        }).done(function(data) {
            // Populate the global data array
            _globals.data = data.files; 
            // Populate the status bar
            _showInfo('Data loaded.');
            var pinfo = _getPagingInfo();
            _populatePagination(pinfo);
            // If a callback function has been passed in, call it
            if(typeof callback === 'function')
                callback();         
        }).fail(function(request, status, error) {
            _showError(error);
        });
    };
    var _loadTags = function(callback) {
        $.ajax({
            url: '/load-tags',
            cache: false,
            type: 'GET',
            dataType: 'json',
        }).done(function(data) {
            // Refresh the tag array *without reassigning the array*, 
            // otherwise tagit autocomplete stops working...
            _globals.tags.length = 0;
            [].push.apply(_globals.tags, data.tags.split('|'));
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
        _globals.index = linearSearch(_globals.data, id);
        var html = _template.viewer({ 
            'path': _globals.data[_globals.index][1]
        });
        _ui.overlay.show();
        _ui.viewer.html(html);
        _ui.viewerContainer.show();
        _ui.viewerPrev.show();
        _ui.viewerNext.show();
        // TODO: Set the height of the overlay AFTER the image has loaded
        // _ui.overlay.height($(document).height());
    };
    var _hideViewer = function() {
        _ui.overlay.hide();
        _ui.viewerContainer.hide();
        _ui.viewerPrev.hide();
        _ui.viewerNext.hide();
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
            _ui.statusMessage = $('#status-message');
            _ui.thumbs = $('#thumbs');
            _ui.pagingInfo = $('#paging-info');
            _ui.pagingPages = $('#paging-pages');
            _ui.pagingPrev = $('#paging-prev');
            _ui.pagingNext = $('#paging-next');
            _ui.syncNow = $('#sync-now');
            _ui.overlay = $('#overlay');
            _ui.viewer = $('#large-image');
            _ui.viewerContainer = $('#large-image-container');
            _ui.mainContainer = $('#container');
            _ui.viewerPrev = $('#viewer-prev');
            _ui.viewerNext = $('#viewer-next');
            // Compile templates
            _template.thumb = Handlebars.compile($('#thumb-template').html());
            _template.pagingInfo = Handlebars.compile($('#paging-info-template').html());
            _template.pagingPage = Handlebars.compile($('#paging-pages-template').html());
            _template.pagingPrev = Handlebars.compile($('#paging-prev-template').html());
            _template.pagingNext = Handlebars.compile($('#paging-next-template').html());
            _template.viewer = Handlebars.compile($('#viewer-template').html());
            _template.infoMessage = Handlebars.compile($('#status-message-info-template').html());
            _template.errorMessage = Handlebars.compile($('#status-message-info-template').html());
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
            // Load a page of results and push to history stack
            var _loadPage = function(e) {
                e.preventDefault();
                e.stopPropagation();
                var page = parseInt($(this).data('page'), 10);
                History.pushState({ page: page, image: null }, 'Page ' + page, '/' + page);
            };
            // Handle click on a page number link
            _ui.pagingPages.on('click', 'a', _loadPage);
            // Handle previous page link click
            _ui.pagingPrev.on('click', 'a', _loadPage);
            // Handle previous page link click
            _ui.pagingNext.on('click', 'a', _loadPage);
            // Handle sync button click
            _ui.syncNow.on('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                _sync();
            });
            // Handle reload link click
            _ui.statusMessage.on('click', '#reload', function(e) {
                e.preventDefault();
                e.stopPropagation();
                alert('TODO: reload global data array at this point!');
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
                _search(_ui.queryInput.val());
            });
            // Handle cancel button click
            _ui.viewerContainer.on('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                var pageId = _globals.page;
                History.pushState({ page: pageId, image: null }, 'Page ' + pageId, '/' + pageId);
            });
            // Load an image in the viewer and push to history stack
            var _loadImage = function(i) {
                _globals.index += i;
                var id = _globals.data[_globals.index][0];
                // If the thumbnail of the image we're viewing isn't in the underlying
                // thumbnail grid, load the previous page in the background
                if(!$('#i-' + id).length) {
                    _globals.page += i
                    _page(_globals.page);
                }
                History.pushState({ page: null, image: id }, 'Image ' + id, '/file/' + id);
            };
            // Handle viewer previous button click
            _ui.viewerPrev.on('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                _loadImage(-1);
            });
            // Handle viewer next button click
            _ui.viewerNext.on('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                _loadImage(1);
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
                if (_globals.syncing)
                    return 'A sync is currently in progress.';
            });
            // Bind to History.js state change
            $(window).bind('statechange', function() {
                // Log the state
                var state = History.getState(); 
                History.debug('statechange:', state.data, state.title, state.url);
                _hideViewer();
                if(state.title === '') {
                    _globals.page = 1;
                    _page(_globals.page);
                } else {
                    // If the state contains a page ID, load the page
                    if(state.data.page) {
                        _globals.page = state.data.page;
                        _page(_globals.page);
                    } else if(state.data.image) { // If the state contains an image ID, load it
                        _view(state.data.image);
                    }
                }
            });
            // If we've got a file ID
            if(file > 0) {
                _loadFiles(function() { 
                    _view(file); 
                    // TODO: Why doesn't this work here? statechange handler is never fired...
                    // History.pushState({ page: null, image: file }, 'Image ' + file, '/file/' + file);
                    // Figure out which page the file is on, then load it in the background
                    var index = linearSearch(_globals.data, file);
                    var filePage = Math.ceil((index + 1) / _config.PAGE_SIZE);
                    _page(filePage);
                });
            } else {
                _loadFiles(function() {
                    _page(page);
                });
            }
            _loadTags(_sync);
        },
        globals: _globals,
        ui: _ui
    }
}(jQuery, Handlebars, History));