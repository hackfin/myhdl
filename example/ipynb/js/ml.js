define([
    'base/js/namespace'
], function(
    Jupyter
) {
    console.log("Language switcher working!");
    var show_selected_language = function(language) {
        language = String.toLowerCase(language);
        console.log("switching languages...");
        // Find all cells with specific language
        var cells = Jupyter.notebook.get_cells();

        cells.forEach(function(cell) {
            if(cell.hasOwnProperty("metadata") && cell.metadata.hasOwnProperty("tags") && cell.metadata.tags.indexOf(language) !== -1) {
                cell.element.show('slow');
            } else if (cell.hasOwnProperty("metadata") && cell.metadata.hasOwnProperty("tags") && cell.metadata.tags.indexOf(language) === -1) {
                cell.element.hide('slow');
            }
        });
    };

    var load_ipython_extension = function() {        
        var lang_dropdown =  $("<div/>").addClass("dropdown btn-group").attr("id","lang-menu");
        var lang_button  = $("<button/>")
                      .addClass("btn btn-default dropdown-toggle")
                      .attr("type","button")
                      .attr("data-toggle","dropdown")
                      .attr("title", "Switch Language")
                      .text("Language");
        var lang_caret = $("<span>").addClass("caret");
        lang_button.append(lang_caret);

        var lang_dropdown_ul = $("<ul/>")
            .attr("id","lang_menu")
            .addClass("dropdown-menu");

        lang_dropdown.append(lang_button).append(lang_dropdown_ul);

        $(Jupyter.toolbar.selector).append(lang_dropdown);

        function add_new_item(menu, display_text, id) {
            menu.append($("<li/>").attr("id",id)
                                              .append($("<a/>")
                                                      .attr("href","#")
                                                      .text(display_text))
                                                      .click(function() { show_selected_language(display_text);}));
        }
        add_new_item(lang_dropdown_ul, "English", "switch-lang-english");
        add_new_item(lang_dropdown_ul, "Deutsch", "switch-lang-deutsch");


        var english_action = {
            help: "Switch language to English",
            help_index: "a",
            icon: "fa-language",
            handler : function() { show_selected_language("english");},
        };

        var english_prefix = "language_switcher";
        var english_action_name = "switch-lang-english";

        Jupyter.actions.register(english_action, english_action_name, english_prefix);

        var deutsch_action = {
            help: "Switch language to Spanish",
            help_index: "a",
            icon: "fa-language",
            handler : function() { show_selected_language("deutsch");},
        };

        var deutsch_prefix = "language_switcher";
        var deutsch_action_name = "switch-lang-deutsch";


        Jupyter.actions.register(deutsch_action, deutsch_action_name, deutsch_prefix);
    };

    return {
        load_ipython_extension : load_ipython_extension
    };
});
